import { useState, useCallback } from 'react';

export function useOptimisticUpdates<T>(initialData: T[]) {
  const [data, setData] = useState<T[]>(initialData);
  const [optimisticUpdates, setOptimisticUpdates] = useState<Map<string, T>>(new Map());

  const addOptimistic = useCallback((id: string, item: T) => {
    setOptimisticUpdates(prev => new Map(prev).set(id, item));
  }, []);

  const confirmOptimistic = useCallback((id: string, confirmedItem: T) => {
    setOptimisticUpdates(prev => {
      const newMap = new Map(prev);
      newMap.delete(id);
      return newMap;
    });
    setData(prev => prev.map(item => 
      (item as any).id === id ? confirmedItem : item
    ));
  }, []);

  const revertOptimistic = useCallback((id: string) => {
    setOptimisticUpdates(prev => {
      const newMap = new Map(prev);
      newMap.delete(id);
      return newMap;
    });
  }, []);

  return {
    data: [...data, ...Array.from(optimisticUpdates.values())],
    addOptimistic,
    confirmOptimistic,
    revertOptimistic
  };
}