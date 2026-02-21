# Mobile WebView Template

This folder contains the shared Flutter WebView entry file:
- `lib/main.dart`

Create the real mobile project (Android + iOS) with:

```bash
./scripts/create_mobile_shell.sh
```

The script will generate:
- `mobile_shell/` Flutter project
- `mobile_shell/lib/main.dart` from this template
- `webview_flutter` dependency installed

Theme behavior:
- `System` sends no `theme` query parameter
- `Light` sends `?theme=light`
- `Dark` sends `?theme=dark`

The Streamlit app applies this query parameter for light/dark rendering.
