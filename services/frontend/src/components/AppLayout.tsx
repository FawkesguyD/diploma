import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { LogOut, Menu, Newspaper, Database, Building2, TrendingDown, BarChart3, Map as MapIcon } from 'lucide-react';
import { useAuth } from '@/auth/AuthProvider';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ThemeToggle } from '@/components/theme-toggle';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { useState } from 'react';

interface NavItem {
  to: string;
  label: string;
  icon: typeof Newspaper;
  adminOnly?: boolean;
}

const NAV: NavItem[] = [
  { to: '/messages', label: 'Лента', icon: Newspaper },
  { to: '/sources', label: 'Источники', icon: Database, adminOnly: false },
  { to: '/objects', label: 'Объекты', icon: Building2 },
  { to: '/objects/top-undervalued', label: 'Топ недооценённых', icon: TrendingDown },
  { to: '/dashboards', label: 'Дашборды', icon: BarChart3 },
  { to: '/map', label: 'Карта', icon: MapIcon },
];

export function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-4 px-4 sm:px-6">
          <button
            type="button"
            className="flex items-center gap-2 font-semibold tracking-tight"
            onClick={() => navigate('/messages')}
          >
            <span className="grid h-7 w-7 place-items-center rounded-md bg-primary text-primary-foreground text-xs font-bold">
              АИС
            </span>
            <span className="hidden sm:inline">Информационные потоки</span>
          </button>

          <nav className="ml-6 hidden items-center gap-1 lg:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/messages'}
                className={({ isActive }) =>
                  cn(
                    'inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground',
                    isActive && 'bg-accent text-accent-foreground'
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen((v) => !v)}>
              <Menu className="h-4 w-4" />
            </Button>
            {user && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="gap-2">
                    <span className="grid h-7 w-7 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                      {user.email[0]?.toUpperCase()}
                    </span>
                    <span className="hidden text-sm sm:inline">{user.display_name || user.email}</span>
                    <Badge variant={user.role === 'admin' ? 'default' : 'muted'} className="hidden sm:inline-flex">
                      {user.role}
                    </Badge>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel>
                    <div className="font-medium">{user.display_name || 'Аккаунт'}</div>
                    <div className="text-xs text-muted-foreground">{user.email}</div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={logout}>
                    <LogOut className="h-4 w-4" />
                    Выйти
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>

        {mobileOpen && (
          <div className="border-t border-border/60 bg-background lg:hidden">
            <nav className="flex flex-col p-2">
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/messages'}
                  onClick={() => setMobileOpen(false)}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                      isActive && 'bg-accent text-accent-foreground'
                    )
                  }
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        )}
      </header>

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>
    </div>
  );
}
