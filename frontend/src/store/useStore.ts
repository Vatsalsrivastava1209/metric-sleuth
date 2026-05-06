import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export interface JobState {
  state: string;
  metric: string;
  startedAt: number;
}

export interface UserProfile {
  id: string;
  subscription_tier: string;
  payment_failed_at?: string | null;
}

interface AppState {
  activeDatasetId: string | null;
  setActiveDatasetId: (id: string | null) => void;
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
  
  activeJobs: Record<string, JobState>;
  setJob: (jobId: string, jobData: JobState) => void;
  removeJob: (jobId: string) => void;
  
  profile: UserProfile | null;
  setProfile: (profile: UserProfile | null) => void;
}

// P1-C: Jobs older than 30 minutes are considered stale and pruned on
// rehydration. Analysis pipelines have a 1-hour hard Celery timeout, so any
// job that isn't resolved within 30 minutes is almost certainly dead.
const JOB_TTL_MS = 30 * 60 * 1000;

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      activeDatasetId: null,
      setActiveDatasetId: (id) => set({ activeDatasetId: id }),
      isSidebarOpen: true,
      toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
      
      activeJobs: {},
      setJob: (jobId, jobData) => 
        set((state) => ({
          activeJobs: { ...state.activeJobs, [jobId]: jobData }
        })),
      removeJob: (jobId) => 
        set((state) => {
          const remaining = { ...state.activeJobs };
          delete remaining[jobId];
          return { activeJobs: remaining };
        }),
        
      profile: null,
      setProfile: (profile) => set({ profile })
    }),
    {
      name: 'metricsleuth-store',
      storage: createJSONStorage(() => typeof window !== 'undefined' ? localStorage : ({} as Storage)),
      partialize: (state) => ({ 
        activeDatasetId: state.activeDatasetId,
        isSidebarOpen: state.isSidebarOpen,
        activeJobs: state.activeJobs 
      }),
      // P1-C: Prune stale jobs on every store rehydration (page load / tab focus).
      // Jobs that started more than JOB_TTL_MS ago are evicted from localStorage
      // so returning users don't see phantom spinners for long-dead analyses.
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        const cutoff = Date.now() - JOB_TTL_MS;
        const pruned = Object.fromEntries(
          Object.entries(state.activeJobs).filter(([, job]) => job.startedAt > cutoff)
        );
        state.activeJobs = pruned;
      },
    }
  )
);

