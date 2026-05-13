type UserLike = {
  role?: string;
  is_admin?: boolean;
  capabilities?: string[];
} | null | undefined;

export function isAdminUser(user: UserLike): boolean {
  if (!user) return false;
  if (user.is_admin) return true;
  if (Array.isArray(user.capabilities) && user.capabilities.includes('admin.panel')) return true;
  return user.role === 'admin';
}

