import type { Accountability } from '@directus/types';

declare global {
  namespace Express {
    interface Request { accountability?: Accountability | null }
  }
}
