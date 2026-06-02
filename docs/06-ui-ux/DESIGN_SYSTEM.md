# Design System

## Direction
Use a quiet, work-focused SaaS dashboard style. Prioritize dense but readable tables, clear approvals, restrained colors, predictable navigation, and fast scanning.

## Foundations
| Element | Decision |
| --- | --- |
| UI library | shadcn/ui |
| Styling | Tailwind CSS |
| Icons | lucide-react where available |
| Charts | Recharts |
| Radius | 8px or less unless component default requires otherwise |
| Tables | Sticky headers for large review grids where practical |
| Dark mode | Use the `/agents` page language: slate-950 panels, `white/10` borders, translucent `white/5` controls, muted slate text, and restrained indigo/emerald accents. Avoid light-only `bg-white` workflow cards, forms, and tables without `dark:*` variants. |
| Dropdowns | Use the shared `Select` for filters. Menus may be wider than the trigger so option labels stay readable, with clear selected-row treatment and dark-mode contrast. |

## Interaction Rules
- Use badges for statuses.
- Use confirmation dialogs for approvals.
- Use tooltips for unfamiliar icons.
- Avoid marketing-style hero layouts inside the app.
- Every shared app header, workflow panel, table shell, form control, error state, and empty state must have a dark-mode treatment.
