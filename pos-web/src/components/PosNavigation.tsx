import {dailyPosDestinations,canLookupStock} from "../navigation/dailyPos";
import type {NavigationActor} from "../navigation/salesReports";
import { useEffect, useState, type ReactNode } from "react";
import {
  ArchiveBoxIcon,
  ArrowRightStartOnRectangleIcon,
  Bars3Icon,
  BuildingStorefrontIcon,
  ChevronDownIcon,
  ClipboardDocumentListIcon,
  Cog6ToothIcon,
  ShoppingCartIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";

import type { PosModuleName } from "../PosModulePage";

type NavigationChild = {
  label: string;
  module: PosModuleName;
  feature?: string;
};

type NavigationGroup = {
  label: string;
  icon: ReactNode;
  feature?:string;
  module?: PosModuleName;
  children?: NavigationChild[];
  visible?: boolean;
};

type Props = {
  canSell?: boolean;
  permissions?:NavigationActor["permissions"];
  open: boolean;
  activeModule: PosModuleName;
  cashierName: string;
  cashierRole: string;
  canManageProducts: boolean;
  canManageInventory: boolean;
  canManageExpenses: boolean;
  canManageCredit: boolean;
  onToggle: () => void;
  onClose: () => void;
  onNavigate: (module: PosModuleName, feature?: string) => void;
  onBackoffice: () => void;
  onLogout: () => void;
};

export default function PosNavigation({
  canSell = true,
  permissions,
  open,
  activeModule,
  cashierName,
  cashierRole,
  onToggle,
  onClose,
  onNavigate,
  onBackoffice,
  onLogout,
}: Props) {
  const [expanded,setExpanded]=useState<Record<string,boolean>>({"Sales activity":true,"Request recovery":true});
  useEffect(()=>{if(["Sales Management","Shift Management"].includes(activeModule))setExpanded(current=>({...current,"Sales activity":true,"Request recovery":true}))},[activeModule]);
  const groups:NavigationGroup[]=[
    {label:"Sales",icon:<ShoppingCartIcon/>,module:"Sales",visible:canSell},
    {label:"Business Operations",icon:<BuildingStorefrontIcon/>,module:"Business Operations"},
    {label:"Sales activity",icon:<ClipboardDocumentListIcon/>,children:dailyPosDestinations({role:cashierRole,permissions}).map(item=>({label:item.title,module:item.module,feature:item.feature}))},
    {label:"Request recovery",icon:<ClipboardDocumentListIcon/>,module:"Sales Management",feature:"request-recovery"},
    {label:"Stock lookup",icon:<ArchiveBoxIcon/>,module:"Inventory",visible:canLookupStock({role:cashierRole,permissions})},
    {label:"Device settings",icon:<Cog6ToothIcon/>,module:"Settings"},
  ];

  const isGroupActive = (group: NavigationGroup) =>
    group.module === activeModule || group.children?.some((child) => child.module === activeModule);

  return <>
    <button
      type="button"
      className="pos-menu-trigger"
      aria-label={open ? "Collapse POS menu" : "Open POS menu"}
      aria-expanded={open}
      onClick={onToggle}
    >
      {open ? <XMarkIcon /> : <Bars3Icon />}
    </button>

    {open && <button type="button" className="pos-menu-overlay" aria-label="Close POS menu" onClick={onClose} />}

    <aside className={`pos-menu-panel ${open ? "is-open" : ""}`} aria-hidden={!open}>
      <div className="pos-menu-brand-row">
        <span className="pos-brand-mark" aria-hidden="true">A</span>
        <div><strong>ApexRetail POS</strong><span>Retail workspace</span></div>
      </div>

      <div className="pos-menu-session">
        <span className="pos-session-avatar" aria-hidden="true">{cashierName.trim().slice(0, 1).toUpperCase() || "A"}</span>
        <div><strong>{cashierName || "Cashier"}</strong><span>{cashierRole || "employee"}</span></div>
      </div>

      <nav className="pos-menu-navigation" aria-label="POS navigation">
        {groups.filter((group) => group.visible !== false).map((group) => {
          const active = Boolean(isGroupActive(group));
          if (!group.children) {
            return <button key={group.label} type="button" className={active ? "active" : ""} onClick={() => group.module && onNavigate(group.module,group.feature)}>
              {group.icon}<span>{group.label}</span>
            </button>;
          }
          const isExpanded = Boolean(expanded[group.label]);
          return <div className={`pos-nav-group ${active ? "active" : ""}`} key={group.label}>
            <button
              type="button"
              className="pos-nav-group-toggle"
              aria-expanded={isExpanded}
              onClick={() => setExpanded((current) => ({ ...current, [group.label]: !isExpanded }))}
            >
              {group.icon}<span>{group.label}</span><ChevronDownIcon className={`pos-nav-chevron ${isExpanded ? "expanded" : ""}`} />
            </button>
            {isExpanded && <div className="pos-nav-children">
              {group.children.map((child) => <button
                type="button"
                className={activeModule === child.module ? "active" : ""}
                key={child.label}
                onClick={() => onNavigate(child.module, child.feature)}
              >{child.label}</button>)}
            </div>}
          </div>;
        })}

        <button type="button" onClick={onBackoffice}><BuildingStorefrontIcon /><span>Open Backoffice</span></button>
      </nav>

      <button type="button" className="pos-menu-logout" onClick={onLogout}>
        <ArrowRightStartOnRectangleIcon /><span>Log out</span>
      </button>
    </aside>
  </>;
}
