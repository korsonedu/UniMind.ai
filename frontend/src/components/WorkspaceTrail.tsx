import { CaretRight } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';

export function WorkspaceTrail({ title, crumbs }: {
  title: string; crumbs: { label: string; to?: string }[];
}) {
  return <div className="um-workspace-trail">
    <nav aria-label="当前位置">{crumbs.filter(crumb => crumb.label).map((crumb, index) => <span className="um-workspace-crumb" key={index}>{crumb.to ? <Link to={crumb.to}>{crumb.label}</Link> : <span>{crumb.label}</span>}<CaretRight size={12} /></span>)}<strong aria-current="page" title={title}>{title}</strong></nav>
  </div>;
}
