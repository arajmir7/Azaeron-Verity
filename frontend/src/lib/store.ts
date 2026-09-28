/** AZAERON global state store */
import { create } from "zustand";

export type ProductRole = "student" | "teacher" | "professor" | "researcher" | "reviewer" | "institution";

export interface User {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  is_active: boolean;
  is_verified: boolean;
  mfa_enabled?: boolean;
  active_organization_id?: string | null;
  product_role?: ProductRole | null;
  onboarding_completed?: boolean;
  home_path?: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  subscription_tier?: string;
  role?: string;
}

export type OrganizationState =
  | "loading"
  | "no_organization"
  | "selection_required"
  | "selecting"
  | "active"
  | "selection_failed";

interface AppState {
  user: User | null;
  organizations: Organization[];
  currentOrg: Organization | null;
  organizationState: OrganizationState;
  organizationError: string | null;
  isLoading: boolean;
  setUser: (user: User | null) => void;
  setOrganizations: (orgs: Organization[]) => void;
  setCurrentOrg: (org: Organization | null) => void;
  setOrganizationState: (state: OrganizationState, error?: string | null) => void;
  setLoading: (loading: boolean) => void;
  logout: (clearDrafts?: boolean) => void;
}

export const useStore = create<AppState>((set) => ({
  user: null,
  organizations: [],
  currentOrg: null,
  organizationState: "loading",
  organizationError: null,
  isLoading: true,
  setUser: (user) => set({ user }),
  setOrganizations: (organizations) => set({ organizations }),
  setCurrentOrg: (currentOrg) => set({ currentOrg, organizationState: currentOrg ? "active" : "no_organization", organizationError: null }),
  setOrganizationState: (organizationState, organizationError = null) => set({ organizationState, organizationError }),
  setLoading: (isLoading) => set({ isLoading }),
  logout: (clearDrafts = false) => {
    try {
      for (const key of Object.keys(sessionStorage)) if (clearDrafts && key.startsWith("verity:draft:v1:")) sessionStorage.removeItem(key);
    } catch { /* Sign-out must succeed when browser storage is unavailable. */ }
    set({ user: null, organizations: [], currentOrg: null, organizationState: "loading", organizationError: null, isLoading: false });
  },
}));
