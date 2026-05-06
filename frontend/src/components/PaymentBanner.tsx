'use client';

import { useState, useEffect } from 'react';
import { AlertCircle } from 'lucide-react';
import { useStore } from '../store/useStore';

export function PaymentBanner() {
  const profile = useStore((state) => state.profile);
  const [hydrated, setHydrated] = useState(() => useStore.persist.hasHydrated());

  useEffect(() => {
    const unsubscribe = useStore.persist.onFinishHydration(() => {
      setHydrated(true);
    });

    return unsubscribe;
  }, []);

  if (!hydrated) return null;
  if (!profile?.payment_failed_at) return null;

  return (
    <div className="w-full bg-destructive/15 text-destructive-foreground px-4 py-3 flex items-center justify-center gap-3 border-b border-destructive/20 shadow-sm z-50">
      <AlertCircle className="w-5 h-5 flex-shrink-0 text-destructive" />
      <span className="text-sm font-medium">
        We were unable to process your most recent subscription payment. Please update your billing details to maintain uninterrupted enterprise access.
      </span>
      <a 
        href="/login" 
        className="text-sm border border-destructive/50 hover:bg-destructive/10 px-3 py-1 rounded transition-colors"
      >
        Manage Subscription
      </a>
    </div>
  );
}
