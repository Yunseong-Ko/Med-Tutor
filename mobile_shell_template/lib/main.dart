import "package:flutter/material.dart";
import "package:webview_flutter/webview_flutter.dart";

const String kDefaultBaseUrl = String.fromEnvironment(
  "AXIOMAQ_BASE_URL",
  defaultValue: "https://axiomaq-6rexvkqrgs6buvgv8oebmr.streamlit.app/",
);

enum MobileThemeMode {
  system,
  light,
  dark,
}

void main() {
  runApp(const AxiomaQbankMobileApp());
}

class AxiomaQbankMobileApp extends StatefulWidget {
  const AxiomaQbankMobileApp({super.key});

  @override
  State<AxiomaQbankMobileApp> createState() => _AxiomaQbankMobileAppState();
}

class _AxiomaQbankMobileAppState extends State<AxiomaQbankMobileApp> {
  MobileThemeMode themeMode = MobileThemeMode.system;
  late final WebViewController webViewController;

  @override
  void initState() {
    super.initState();
    webViewController = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0x00000000))
      ..loadRequest(Uri.parse(_buildTargetUrl()));
  }

  String _buildTargetUrl() {
    final Uri base = Uri.parse(kDefaultBaseUrl);
    final Map<String, String> params = <String, String>{
      ...base.queryParameters,
      "mobile": "1",
    };

    if (themeMode == MobileThemeMode.light) {
      params["theme"] = "light";
    } else if (themeMode == MobileThemeMode.dark) {
      params["theme"] = "dark";
    } else {
      params.remove("theme");
    }

    return base.replace(queryParameters: params).toString();
  }

  void _reloadWithTheme(MobileThemeMode nextThemeMode) {
    setState(() {
      themeMode = nextThemeMode;
    });
    webViewController.loadRequest(Uri.parse(_buildTargetUrl()));
  }

  ThemeMode _materialThemeMode() {
    if (themeMode == MobileThemeMode.light) {
      return ThemeMode.light;
    }
    if (themeMode == MobileThemeMode.dark) {
      return ThemeMode.dark;
    }
    return ThemeMode.system;
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: "Axioma Qbank Mobile",
      debugShowCheckedModeBanner: false,
      themeMode: _materialThemeMode(),
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1C7C74)),
        useMaterial3: true,
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF4FC1B6),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: Scaffold(
        appBar: AppBar(
          title: const Text("Axioma Qbank"),
          actions: <Widget>[
            PopupMenuButton<MobileThemeMode>(
              icon: const Icon(Icons.brightness_6_outlined),
              onSelected: _reloadWithTheme,
              itemBuilder: (BuildContext context) =>
                  const <PopupMenuEntry<MobileThemeMode>>[
                PopupMenuItem<MobileThemeMode>(
                  value: MobileThemeMode.system,
                  child: Text("Theme: System"),
                ),
                PopupMenuItem<MobileThemeMode>(
                  value: MobileThemeMode.light,
                  child: Text("Theme: Light"),
                ),
                PopupMenuItem<MobileThemeMode>(
                  value: MobileThemeMode.dark,
                  child: Text("Theme: Dark"),
                ),
              ],
            ),
            IconButton(
              tooltip: "Reload",
              onPressed: () => webViewController.reload(),
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        body: SafeArea(
          child: WebViewWidget(controller: webViewController),
        ),
      ),
    );
  }
}
