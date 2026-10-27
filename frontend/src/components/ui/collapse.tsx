import type { ReactNode } from 'react';
import * as Collapsible from '@radix-ui/react-collapsible';

export function Collapse({ open, id, children }: { open: boolean; id?: string; children: ReactNode }) {
  return <Collapsible.Root open={open} className="um-collapse-root">
    <Collapsible.Content id={id} className="um-collapse" aria-hidden={!open} inert={!open} forceMount>
      {children}
    </Collapsible.Content>
  </Collapsible.Root>;
}
