export interface SiteIdentity { name: string; homeHref: string; }
export interface NavigationLink { href: string; label: string; current?: boolean; }
export interface FooterSection { heading: string; links: readonly NavigationLink[]; text?: string; }
