fn valid_source(url: &tauri::Url, development: bool) -> bool {
  url.username().is_empty() && url.password().is_none() &&
    (url.scheme() == "https" || (development && url.scheme() == "http" &&
      matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "[::1]"))))
}

fn same_origin(source: &tauri::Url, target: &tauri::Url) -> bool {
  target.username().is_empty() && target.password().is_none() && target.origin() == source.origin()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .setup(|app| {
      let development = cfg!(debug_assertions);
      let source = (if development { app.config().build.dev_url.clone() } else { None })
        .or_else(|| match &app.config().build.frontend_dist {
          Some(tauri::utils::config::FrontendDist::Url(url)) => Some(url.clone()),
          _ => None,
        })
        .filter(|url| valid_source(url, development))
        .ok_or_else(|| std::io::Error::other("UniMind requires a trusted HTTPS site or development loopback URL"))?;
      let mut window = app.config().app.windows[0].clone();
      window.url = tauri::WebviewUrl::External(source.clone());
      tauri::WebviewWindowBuilder::from_config(app, &window)?
        .on_navigation(move |url| same_origin(&source, url))
        .on_new_window(|_, _| tauri::webview::NewWindowResponse::Deny)
        .build()?;
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
  use super::*;

  #[test]
  fn navigation_stays_on_the_app_origin() {
    let source = tauri::Url::parse("https://unimind-ai.com/xiaoyu").unwrap();
    assert!(same_origin(&source, &tauri::Url::parse("https://unimind-ai.com/login").unwrap()));
    for target in ["https://unimind-ai.com.evil.test/", "https://evil.test/", "file:///etc/passwd", "javascript:alert(1)", "https://name@unimind-ai.com/"] {
      assert!(!same_origin(&source, &tauri::Url::parse(target).unwrap()));
    }
  }

  #[test]
  fn http_sources_are_development_loopback_only() {
    assert!(valid_source(&tauri::Url::parse("https://unimind-ai.com/").unwrap(), false));
    let local = tauri::Url::parse("http://127.0.0.1:5175/xiaoyu").unwrap();
    assert!(valid_source(&local, true));
    assert!(!valid_source(&local, false));
    assert!(!valid_source(&tauri::Url::parse("http://example.test/").unwrap(), true));
  }
}
