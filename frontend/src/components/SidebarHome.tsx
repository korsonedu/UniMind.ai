import { Plus, ChatCircle, NotePencil, type Icon } from '@phosphor-icons/react';
import type { SidebarView, SidebarRecentItem } from './WorkspaceContext';
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from './ui/dropdown-menu';

interface Tool { id: SidebarView; label: string; icon: Icon }

export function SidebarHome({ tools, added, recent, onSelect, onOpenRecent }: {
  tools: Tool[]; added: SidebarView[]; recent: SidebarRecentItem[]; onSelect: (view: SidebarView) => void; onOpenRecent: (item: SidebarRecentItem) => void;
}) {
  const addedTools = tools.filter(tool => added.includes(tool.id));
  const availableTools = tools.filter(tool => !added.includes(tool.id));
  return <section className="um-sidebar-home" aria-label="侧栏工具入口">
    <section aria-labelledby="sidebar-tools-heading">
      <h3 id="sidebar-tools-heading">工具</h3>
      <div className="um-sidebar-tools">{addedTools.map(tool => <button key={tool.id} type="button" onClick={() => onSelect(tool.id)}><tool.icon size={20} /><span>{tool.label}</span></button>)}
        <DropdownMenu>
          <DropdownMenuTrigger asChild><button type="button" className="um-sidebar-add-tool" aria-label="添加工具"><Plus size={22} /></button></DropdownMenuTrigger>
          <DropdownMenuContent className="um-native-menu" align="start">{!availableTools.length && <DropdownMenuItem disabled>没有更多可添加的工具</DropdownMenuItem>}{availableTools.map(tool => <DropdownMenuItem key={tool.id} onSelect={() => onSelect(tool.id)}><tool.icon size={16} />{tool.label}</DropdownMenuItem>)}</DropdownMenuContent>
        </DropdownMenu>
      </div>
    </section>
    {!!recent.length && <section aria-labelledby="sidebar-recent-heading">
      <h3 id="sidebar-recent-heading">最近使用</h3>
      <div className="um-sidebar-recent">{recent.map(item => <button key={item.key} type="button" onClick={() => onOpenRecent(item)}>{item.view === 'notes' ? <NotePencil size={18} /> : <ChatCircle size={18} />}<span>{item.title}</span></button>)}</div>
    </section>}
  </section>;
}
