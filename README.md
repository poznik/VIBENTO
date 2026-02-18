# layout-autofix

macOS status bar приложение, которое отслеживает смену раскладки (`EN`/`RUS`) и, если есть выделенный текст, конвертирует его в новую раскладку.

## Что умеет

- Работает как приложение в статусбаре macOS.
- Показывает иконку в статусбаре.
- На **правый клик** по иконке открывает меню.
- В меню есть переключатель `Launch At Login` (автозапуск).
- Автозапуск реализован через `~/Library/LaunchAgents`.

## Как это работает

1. Приложение отслеживает смену текущей раскладки ввода.
2. Если в момент переключения есть выделение, выполняется `Cmd+C`.
3. Текст конвертируется в новую раскладку.
4. Выполняется `Cmd+V`, выделение заменяется.
5. Содержимое буфера обмена восстанавливается.

Пример: выделили `ghbdtn`, переключили раскладку на `RUS` -> `привет`.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Запуск

Запуск macOS приложения (status bar):

```bash
layout-autofix-macos
```

CLI-режим без UI (для отладки):

```bash
layout-autofix
```

## Параметры

Для status bar приложения:

```bash
layout-autofix-macos --poll-interval 0.1 --settle-delay 0.02 --layout-switch-settle-delay 0.12 --copy-wait-timeout 0.35 --copy-poll-interval 0.03 --paste-restore-delay 0.2 --log-level INFO
```

В `.app` режиме детальные debug-события включены по умолчанию.  
При запуске из терминала их можно отключить флагом `--no-debug-events`.

Лог пишется в файл:

- `~/Library/Logs/LayoutAutofix/layout-autofix.log` (по умолчанию)

Можно переопределить путь:

```bash
layout-autofix-macos --log-file /tmp/layout-autofix.log
```

Если видите в логе `event=selection_capture_empty reason=clipboard_not_updated`, увеличьте:

- `--layout-switch-settle-delay` (например до `0.2`)
- `--copy-wait-timeout` (например до `0.6`)

## Сборка .app для macOS (без терминала)

```bash
./scripts/build_macos_onefile.sh
```

Результат:

- `dist/LayoutAutofix.app` - обычное macOS приложение.
- Используется иконка `layout-switcher-icon.icns`.

## Права macOS

Нужно выдать приложению (Terminal/iTerm или собранному бинарнику) доступы в:

- `System Settings -> Privacy & Security -> Accessibility`
- `System Settings -> Privacy & Security -> Input Monitoring` (если требуется системой)
