# AGENTS.md

## UI/UX Design Rules
Codex must act as a senior product designer + frontend/mobile engineer.

### Design Quality
- Never generate generic AI-looking UI.
- Before coding UI, define: target user, product tone, visual direction, and layout strategy.
- Use strong visual hierarchy, intentional spacing, consistent radius, shadows, typography, and color tokens.
- Prefer real product UI quality over demo-looking components.
- Treat loading, empty, error, disabled, hover, focus, pressed, and success states as first-class UI states.

### Web Stack
- Prefer React/Next.js + TypeScript for web apps.
- Prefer Tailwind CSS for layout and styling.
- Prefer shadcn/ui + Radix primitives for accessible components.
- Use Storybook-style component isolation when creating reusable UI.
- For enterprise dashboards, MUI or Ant Design is allowed only when explicitly useful.

### iOS Rules
- Follow Apple Human Interface Guidelines.
- Respect iOS conventions: safe areas, bottom reachability, native gestures, Dynamic Type, Dark Mode.
- Avoid Android-style navigation patterns on iOS.
- Prioritize clarity, depth, deference, fluid gestures, and platform-native behavior.

### Android Rules
- Follow Material Design 3.
- Use Material 3 components, typography scale, dynamic color, motion, and adaptive layouts.
- Respect Android navigation, back behavior, touch targets, and system theming.
- Minimum touch target is 48dp.

### React Native / Cross-Platform
- Use React Native Paper for Material-style apps.
- Use Tamagui or NativeWind/gluestack when sharing UI across web + mobile.
- Platform-specific differences are allowed when they improve UX.

### Accessibility
- Minimum touch target: 44px iOS, 48dp Android.
- Support keyboard navigation on web.
- All interactive elements need accessible labels.
- Check contrast, focus states, loading states, empty states, and error states.

### Responsive Behavior
- Design mobile-first.
- Define breakpoints for mobile, tablet, and desktop.
- Avoid fixed pixel layouts unless necessary.
- Test major states: loading, empty, error, success, disabled, hover, focus, and pressed.

### Verification
- After UI changes, run typecheck, lint, tests, or the closest configured validation command.
- For web UI, use Playwright or screenshots to verify layout and interactions.
- For Android, run Gradle assemble/debug validation where possible.
- Report what changed, what was tested, and any remaining UX tradeoffs.
