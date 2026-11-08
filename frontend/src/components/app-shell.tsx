import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, useNavigate } from "@tanstack/react-router";
import {
  Bot,
  BriefcaseBusiness,
  CandlestickChart,
  History,
  LayoutDashboard,
  Menu,
  ScrollText,
  UserCircle,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api, unwrap } from "@/api/client";
import { useLogout, type Me } from "@/auth/auth";
import { Logo } from "@/components/brand";
import { NotAdvice, REPOSITORY, sourceUrl } from "@/components/disclaimer";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTheme, type Theme } from "@/lib/theme";

type NavLabel = "dashboard" | "portfolios" | "policies" | "timeline";
type AdminNavLabel = "accounts" | "aiReviewers" | "priceProviders";

interface NavItem {
  to: string;
  label: NavLabel | AdminNavLabel; // key under nav.*
  icon: LucideIcon;
}

const INVESTOR_NAV: NavItem[] = [
  { to: "/", label: "dashboard", icon: LayoutDashboard },
  { to: "/portfolios", label: "portfolios", icon: BriefcaseBusiness },
  { to: "/policies", label: "policies", icon: ScrollText },
  { to: "/timeline", label: "timeline", icon: History },
];

// The admin role manages accounts, AI reviewers and price providers and sees no investment
// data (USR-05)
const ADMIN_NAV: NavItem[] = [
  { to: "/accounts", label: "accounts", icon: Users },
  { to: "/ai-reviewers", label: "aiReviewers", icon: Bot },
  { to: "/price-providers", label: "priceProviders", icon: CandlestickChart },
];

interface NavGroup {
  heading?: boolean; // shown as "Administration"
  items: NavItem[];
}

/** USR-09: an account with both roles gets both, the admin part under its own heading. */
export function navGroups(me: Me): NavGroup[] {
  if (!me.is_investor) return [{ items: ADMIN_NAV }];
  if (!me.is_admin) return [{ items: INVESTOR_NAV }];
  return [{ items: INVESTOR_NAV }, { heading: true, items: ADMIN_NAV }];
}

function Nav({ me, onNavigate }: { me: Me; onNavigate?: () => void }) {
  const { t } = useTranslation();
  return (
    <nav className="grid gap-1" aria-label={t("nav.main")}>
      {navGroups(me).map((group) => (
        <div key={group.heading ? "admin" : "main"} className="grid gap-1">
          {group.heading && (
            <p className="px-3 pt-3 text-xs font-medium text-muted-foreground">
              {t("nav.administration")}
            </p>
          )}
          {group.items.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              onClick={onNavigate}
              activeOptions={{ exact: to === "/" }}
              className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground [&.active]:bg-accent [&.active]:font-medium [&.active]:text-foreground"
            >
              <Icon className="size-4" aria-hidden />
              {t(`nav.${label}`)}
            </Link>
          ))}
        </div>
      ))}
    </nav>
  );
}

function UserMenu({ me }: { me: Me }) {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();
  const logout = useLogout();
  const navigate = useNavigate();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="w-full justify-start">
          <UserCircle aria-hidden />
          {me.username}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuLabel>{t("userMenu.theme")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme} onValueChange={(v) => setTheme(v as Theme)}>
          <DropdownMenuRadioItem value="system">{t("userMenu.themeSystem")}</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="light">{t("userMenu.themeLight")}</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">{t("userMenu.themeDark")}</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        {/* USR-10: every account has settings, at least the language */}
        <DropdownMenuItem onSelect={() => navigate({ to: "/settings" })}>
          {t("userMenu.settings")}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate({ to: "/password" })}>
          {t("userMenu.changePassword")}
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => logout.mutate(undefined, { onSettled: () => navigate({ to: "/login" }) })}
        >
          {t("userMenu.logOut")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Whether the server runs the version compiled into the frontend; a release candidate's
 * server reports it with -rc.N (section 5.7). In dev the frontend has no version. */
export function sameVersion(compiled: string, server: string): boolean {
  return compiled === "dev" || server === compiled || server.startsWith(`${compiled}-rc.`);
}

/** Version of the running app (section 5.7): the server's, which may add -rc.N to the
 * compiled-in one; both are shown if they differ, e.g. when the browser still runs an
 * older frontend. */
function VersionFooter() {
  const { t } = useTranslation();
  const version = useQuery({
    queryKey: ["version"],
    queryFn: () => unwrap(api.GET("/api/version")),
    staleTime: Infinity,
  });
  const server = version.data;
  const same = server && sameVersion(__APP_VERSION__, server.version);
  const differs = server && !same;
  return (
    <div className="grid gap-1 px-3 text-xs text-muted-foreground">
      <p title={server ? t("footer.commit", { commit: server.commit }) : undefined}>
        {t("footer.version", { version: same ? server.version : __APP_VERSION__ })}
        {differs && t("footer.serverDiffers", { version: server.version })}
      </p>
      {/* NFR-16: source of exactly this build and the licenses (AGPL) */}
      <p className="flex flex-wrap gap-x-2">
        <a href={sourceUrl(server?.commit)} className="underline" target="_blank" rel="noreferrer">
          {t("footer.sourceCode")}
        </a>
        <a
          href={`${REPOSITORY}/blob/main/LICENSE`}
          className="underline"
          target="_blank"
          rel="noreferrer"
        >
          {t("footer.license")}
        </a>
        <a href="/third-party-licenses.txt" className="underline" target="_blank" rel="noreferrer">
          {t("footer.thirdPartyLicenses")}
        </a>
      </p>
      <NotAdvice short={t("notAdvice.short")} className="text-xs" />
    </div>
  );
}

/** Sidebar on wide screens, menu button on phones (NFR-06). */
export function AppShell({ me }: { me: Me }) {
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="min-h-svh md:grid md:grid-cols-[15rem_1fr]">
      <aside className="no-print hidden border-r p-3 md:flex md:flex-col md:gap-4">
        <Logo className="mx-3 mt-2 w-36" />
        <Nav me={me} />
        <div className="mt-auto grid gap-2">
          <UserMenu me={me} />
          <VersionFooter />
        </div>
      </aside>
      <header className="no-print flex items-center gap-2 border-b p-2 md:hidden">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("nav.openMenu")}
          onClick={() => setMenuOpen(true)}
        >
          <Menu />
        </Button>
        <Logo className="w-24" />
      </header>
      <Dialog open={menuOpen} onOpenChange={setMenuOpen}>
        <DialogContent side="left" className="flex flex-col gap-4">
          <DialogTitle>{t("nav.menu")}</DialogTitle>
          <Nav me={me} onNavigate={() => setMenuOpen(false)} />
          <div className="mt-auto grid gap-2">
            <UserMenu me={me} />
            <VersionFooter />
          </div>
        </DialogContent>
      </Dialog>
      <main className="min-w-0 p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  );
}
