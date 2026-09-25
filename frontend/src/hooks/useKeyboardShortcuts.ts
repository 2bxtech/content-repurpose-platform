import { useEffect } from 'react';

interface KeyboardShortcut {
  key: string;
  ctrl?: boolean;
  alt?: boolean;
  shift?: boolean;
  action: () => void;
  description: string;
}

export const useKeyboardShortcuts = (shortcuts: KeyboardShortcut[]) => {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Safety checks for key values
      if (!event.key || !shortcuts.length) return;
      
      const shortcut = shortcuts.find(s => 
        s.key && 
        s.key.toLowerCase() === event.key.toLowerCase() &&
        !!s.ctrl === event.ctrlKey &&
        !!s.alt === event.altKey &&
        !!s.shift === event.shiftKey
      );

      if (shortcut && !event.defaultPrevented) {
        event.preventDefault();
        shortcut.action();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [shortcuts]);

  return shortcuts;
};