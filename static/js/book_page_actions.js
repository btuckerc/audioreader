/**
 * Prompts the user to confirm resetting all progress for a given book.
 * If confirmed, removes relevant playback position and chapter progress
 * data from localStorage for that book.
 *
 * @param {string} bookName - The name of the book to reset.
 * @param {object} allFilesMap - An object where keys are filenames (e.g., chapter1.mp3)
 *                               for the tracks in the book.
 */
async function confirmResetBookProgress(bookName, allFilesMap) {
    if (!bookName || typeof bookName !== 'string' || !bookName.trim()) {
        console.error('[ResetProgress] Invalid or missing bookName.');
        alert('Error: Book name is missing or invalid for resetting progress.');
        return;
    }

    if (confirm(`Are you sure you want to reset all progress for this book: "${bookName}"?\nThis will clear your current chapter marker and all saved playback positions for every chapter in this book from this browser (localStorage and IndexedDB).`)) {
        console.log(`[ResetProgress] User confirmed reset for book: "${bookName}"`);
        try {
            let tracksClearedLS = 0;
            // Clear individual track positions
            if (allFilesMap && typeof allFilesMap === 'object' && Object.keys(allFilesMap).length > 0) {
                Object.keys(allFilesMap).forEach(filename => {
                    if (typeof filename === 'string' && filename.trim()) {
                        const storageKey = `playbackPosition:${bookName}:${filename}`;
                        if (localStorage.getItem(storageKey)) {
                            console.log(`[ResetProgress] Found specific track data for ${filename}. Removing.`);
                            localStorage.removeItem(storageKey);
                            tracksClearedLS++;
                        }
                    }
                });
                console.log(`[ResetProgress][localStorage] Cleared ${tracksClearedLS} individual track positions.`);
            } else {
                console.warn(`[ResetProgress] allFilesMap not available or empty for book "${bookName}". Cannot clear individual track positions precisely by iterating files.`);
            }

            // Clear current chapter marker (this determines the "Resume Reading" banner)
            const chapterProgressRaw = localStorage.getItem('chapterProgress');
            console.log(`[ResetProgress] Raw chapterProgress from localStorage:`, chapterProgressRaw);
            if (chapterProgressRaw) {
                try {
                    const chapterProgress = JSON.parse(chapterProgressRaw);
                    console.log(`[ResetProgress] Parsed chapterProgress:`, chapterProgress);
                    if (chapterProgress && chapterProgress.book === bookName) {
                        console.log(`[ResetProgress] chapterProgress is for this book. Removing.`);
                        localStorage.removeItem('chapterProgress');
                    } else {
                        console.log(`[ResetProgress] chapterProgress is for a different book or invalid.`);
                    }
                } catch (e) {
                    console.error('[ResetProgress] Error parsing chapterProgress from localStorage:', e);
                }
            }

            // Clear general playbackPosition (often the most recent chapter listened to across all books)
            const generalPlaybackPositionRaw = localStorage.getItem('playbackPosition');
            console.log(`[ResetProgress] Raw generalPlaybackPosition from localStorage:`, generalPlaybackPositionRaw);
            if (generalPlaybackPositionRaw) {
                try {
                    const generalPosition = JSON.parse(generalPlaybackPositionRaw);
                    console.log(`[ResetProgress] Parsed generalPlaybackPosition:`, generalPosition);
                    if (generalPosition && generalPosition.book === bookName) {
                        // Also check if currentTime exists and is > 0, to avoid issues if it was somehow a malformed/reset entry
                        // However, for a full reset, if it matches the book, it should probably be cleared regardless of currentTime value.
                        console.log(`[ResetProgress] generalPlaybackPosition is for this book. Removing.`);
                        localStorage.removeItem('playbackPosition');
                    } else {
                        console.log(`[ResetProgress] generalPlaybackPosition is for a different book or invalid.`);
                    }
                } catch (e) {
                    console.error('[ResetProgress] Error parsing general playbackPosition:', e);
                }
            }
            console.log('[ResetProgress][localStorage] Deletion attempts complete.');

            // --- IndexedDB Deletion ---
            console.log('[ResetProgress] Attempting to clear IndexedDB progress...');
            await clearBookIndexedDBProgress(bookName, allFilesMap);
            console.log('[ResetProgress] IndexedDB progress clearing process finished.');

            alert(`Progress for "${bookName}" has been reset in this browser. The page will now reload.`);
            window.location.reload();
        } catch (error) {
            console.error('[ResetProgress] Error during reset process:', error);
            alert('An error occurred while resetting book progress. Check the console for details. Some progress might still exist in IndexedDB if that stage failed.');
        }
    } else {
        console.log('[ResetProgress] User cancelled reset.');
    }
}

/**
 * Checks if there is any stored progress for the given book.
 * @param {string} bookName - The name of the book.
 * @param {object} allFilesMap - An object where keys are filenames for the tracks in the book.
 * @returns {boolean} - True if progress is found, false otherwise.
 */
function hasBookProgress(bookName, allFilesMap) {
    if (!bookName || typeof bookName !== 'string') {
        return false;
    }

    // Check current chapter marker
    const chapterProgressRaw = localStorage.getItem('chapterProgress');
    if (chapterProgressRaw) {
        try {
            const chapterProgress = JSON.parse(chapterProgressRaw);
            if (chapterProgress && chapterProgress.book === bookName) {
                return true;
            }
        } catch (e) { /* ignore parse error */ }
    }

    // Check general playbackPosition (often the most recent overall)
    const generalPlaybackPositionRaw = localStorage.getItem('playbackPosition');
    if (generalPlaybackPositionRaw) {
        try {
            const generalPosition = JSON.parse(generalPlaybackPositionRaw);
            if (generalPosition && generalPosition.book === bookName && generalPosition.currentTime > 0) {
                return true;
            }
        } catch (e) { /* ignore parse error */ }
    }

    // Check individual track positions
    if (allFilesMap && typeof allFilesMap === 'object') {
        for (const filename of Object.keys(allFilesMap)) {
            if (typeof filename === 'string' && filename.trim()) {
                const storageKey = `playbackPosition:${bookName}:${filename}`;
                const trackPositionRaw = localStorage.getItem(storageKey);
                if (trackPositionRaw) {
                    try {
                        const trackPosition = JSON.parse(trackPositionRaw);
                        if (trackPosition && trackPosition.currentTime > 0) {
                            return true;
                        }
                    } catch (e) { /* ignore parse error */ }
                }
            }
        }
    }
    return false;
}

async function clearBookIndexedDBProgress(bookName, allFilesMap) {
    return new Promise((resolve, reject) => {
        const dbName = 'AudiobookPlayer';
        const storeName = 'playback';
        const version = 1; // Ensure this matches the version in player.html

        const request = indexedDB.open(dbName, version);

        request.onerror = (event) => {
            console.error('[ResetProgress][IndexedDB] Database error:', event.target.error);
            reject(event.target.error);
        };

        request.onsuccess = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(storeName)) {
                console.warn(`[ResetProgress][IndexedDB] Object store "${storeName}" not found.`);
                db.close();
                resolve(); // Resolve even if store not found, as there's nothing to clear from it.
                return;
            }

            try {
                const transaction = db.transaction([storeName], 'readwrite');
                const store = transaction.objectStore(storeName);
                let deleteCount = 0;
                const totalDeletionsNeededEstimate = (allFilesMap ? Object.keys(allFilesMap).length : 0) + 1; // +1 for chapter progress

                const onCompleteOrError = (operation) => {
                    // This is a simplified way to check completion.
                    // Proper transaction.oncomplete is better for final resolve.
                };

                // 1. Delete chapter progress key
                const chapterProgressKey = `chapter:${bookName}`;
                const deleteChapterRequest = store.delete(chapterProgressKey);
                deleteChapterRequest.onsuccess = () => {
                    console.log(`[ResetProgress][IndexedDB] Successfully requested deletion of chapter progress: ${chapterProgressKey}`);
                    deleteCount++;
                };
                deleteChapterRequest.onerror = (e) => {
                    console.error(`[ResetProgress][IndexedDB] Error deleting chapter progress ${chapterProgressKey}:`, e.target.error);
                };

                // 2. Delete individual track positions
                if (allFilesMap && typeof allFilesMap === 'object') {
                    Object.keys(allFilesMap).forEach(filename => {
                        if (typeof filename === 'string' && filename.trim()) {
                            const trackKey = `${bookName}:${filename}`;
                            const deleteTrackRequest = store.delete(trackKey);
                            deleteTrackRequest.onsuccess = () => {
                                console.log(`[ResetProgress][IndexedDB] Successfully requested deletion of track: ${trackKey}`);
                                deleteCount++;
                            };
                            deleteTrackRequest.onerror = (e) => {
                                console.error(`[ResetProgress][IndexedDB] Error deleting track ${trackKey}:`, e.target.error);
                            };
                        }
                    });
                }

                transaction.oncomplete = () => {
                    console.log('[ResetProgress][IndexedDB] All delete operations complete.');
                    db.close();
                    resolve();
                };

                transaction.onerror = (event) => {
                    console.error('[ResetProgress][IndexedDB] Transaction error:', event.target.error);
                    db.close();
                    reject(event.target.error);
                };

            } catch (e) {
                console.error('[ResetProgress][IndexedDB] Error initiating transaction or operations:', e);
                db.close();
                reject(e);
            }
        };

        request.onupgradeneeded = (event) => {
            // This should ideally not be hit if player.html has already established the DB structure.
            // If it is hit, it means the DB didn't exist or version was bumped.
            console.log('[ResetProgress][IndexedDB] onupgradeneeded triggered. DB structure might be getting created.');
            // Let player.html handle actual creation. For reset, we just need to operate on existing if possible.
            // We can proceed, and onsuccess will check if the store exists.
        };
    });
}
