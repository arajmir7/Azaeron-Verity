/** Hydrate tenant state only after the server validates workspace membership. */
import { api, ApiError, type UserProfile } from "@/lib/api";
import { useStore, type Organization } from "@/lib/store";

function recentWorkspace(userId: string, workspaceId?: string) {
  try {
    const key = `azaeron:recent-workspace:${userId}`;
    if (workspaceId) localStorage.setItem(key, workspaceId);
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function workspaceHome(profile: UserProfile) {
  return profile.onboarding_completed ? profile.home_path || "/dashboard" : "/onboarding";
}

export async function selectWorkspace(workspace: Organization) {
  const state = useStore.getState();
  state.setOrganizationState("selecting");
  try {
    const selected = await api.selectOrganization(workspace.id);
    state.setCurrentOrg({ ...selected, role: workspace.role });
    if (state.user) recentWorkspace(state.user.id, selected.id);
    return selected;
  } catch (reason) {
    // A failed cookie-changing request may have reached the server. Revalidate
    // scope before mounting any document views again.
    state.setCurrentOrg(null);
    state.setOrganizationState("selection_failed", reason instanceof Error ? reason.message : "Unable to switch workspace.");
    throw reason;
  }
}

let pendingSession: Promise<UserProfile> | null = null;

export function loadWorkspaceSession(profile?: UserProfile): Promise<UserProfile> {
  if (pendingSession) return pendingSession;
  const state = useStore.getState();
  state.setLoading(true);
  state.setCurrentOrg(null);
  pendingSession = (async () => {
    try {
      const me = profile || await api.getMe();
      state.setUser(me);
      const records = await api.getOrganizations();
      const roles = new Map(me.organizations.filter((membership) => membership.is_active).map((membership) => [membership.organization_id, membership.role]));
      const organizations = records.map((organization) => ({ ...organization, role: roles.get(organization.id) }));
      state.setOrganizations(organizations);
      if (!me.onboarding_completed || organizations.length === 0) return me;
      const preferredId = me.active_organization_id || recentWorkspace(me.id);
      const preferred = organizations.find((organization) => organization.id === preferredId);
      const candidates = preferred ? [preferred, ...organizations.filter((organization) => organization.id !== preferred.id)] : organizations;
      for (const organization of candidates) {
        try {
          await selectWorkspace(organization);
          return me;
        } catch (reason) {
          if (!(reason instanceof ApiError) || ![403, 404].includes(reason.status)) throw reason;
          // A membership may have been revoked since the list was fetched.
          state.setOrganizations(useStore.getState().organizations.filter((item) => item.id !== organization.id));
        }
      }
      state.setCurrentOrg(null);
      return me;
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) state.logout();
      state.setOrganizationState("selection_failed", reason instanceof Error ? reason.message : "Unable to open your workspace.");
      throw reason;
    } finally {
      state.setLoading(false);
      pendingSession = null;
    }
  })();
  return pendingSession;
}
