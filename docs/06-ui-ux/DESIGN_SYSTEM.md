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

## Interaction Rules
- Use badges for statuses.
- Use confirmation dialogs for approvals.
- Use tooltips for unfamiliar icons.
- Avoid marketing-style hero layouts inside the app.

