# Obnova repozitára (RECOVERY)

Tento repozitár bol obnovený 21. 11. 2026 z textovej zálohy projektu „aurelvi-ha“ v claude.ai
(snapshot z 28. 10. 2026), pretože pôvodný GitHub účet `sonics007` bol zrušený.
História commitov sa nezachovala – toto je nový počiatočný commit.

## Čo chýba (nebolo v zálohe)

- Binárne súbory: obrázky (webp/png), zvuky (wav), APK súbory, ZIP archívy.
- Jazykové súbory okrem angličtiny a slovenčiny (pôvodne 26 jazykov v `locale/`).
  Testy, ktoré očakávajú 26 jazykov, preto zlyhajú, kým sa nedoplnia.
- Pribalená knižnica `jssip.min.js` (interkom). `sendspin.js` bol obnovený z APK 0.3.0.
- Podpisový kľúč APK (keystore) a súkromný licenčný kľúč – tieto nikdy neboli v Gite.

## Čo bolo pregenerované

- `tools/build_locales.py` vygeneroval `i18n.js`, `frontend/locale/*.json`,
  `translations/*.json` a `strings.json` z `locale/en.json` a `locale/sk.json`.
- `android/assets/` je kópia frontendu z aurelvi-ha (bez Studia).
- `android/examples/*.json` a `THIRD_PARTY_NOTICES.txt` boli zostavené zo zachovaných zdrojov.

Všetky odkazy na pôvodný účet `sonics007` (zdroj aktualizácií, workflowy, README, web, manifest, LICENSE) boli prepísané na `soso8782`.

## Náhrady doplnené po obnove

- **Textúry materiálov** (`materials/*.webp`): pôvodné fotografické skeny chýbajú, nahradili ich
  procedurálne vygenerované textúry (`aurelvi-ha/tools/generate-placeholder-materials.py`).
  Pre pôvodný vzhľad nahraď súbory skutočnými skenmi s rovnakými názvami.
- **Zvuky** (`sounds/*.wav`): `alarm_beep`, `alarm`, `alarmo`, `ding` a `siren` sú originály z APK 0.3.0;
  tóny `alarm-birds`, `alarm-dawn`, `alarm-chimes` sú vygenerované pôvodným skriptom
  `android/tests/generate-alarm-tones.py` (deterministický, rovnaký ako originál).
- **Logo webu a APK README** (`logo.svg`): kópia symbolu `logo-symbol.svg`.
- **Testy:** kontroly nemeckého textu sa preskočia, kým nie je obnovený `locale/de.json`.
- **Publikovanie APK:** workflow sa bez súboru v `dist/` ukončí s upozornením namiesto chyby.
- **Obrázky webu a Studia** (`website/assets/*.webp`, `theme-atlas.webp`, `studio.png`): znova vyfotené
  z aktuálnej aplikácie pôvodnými skriptmi `website-tests/` (Studio novým `website-tests/studio-capture.mjs`),
  takže zobrazujú náhradné textúry. `website/assets/skins.js` je kópia `frontend/skins.js`.
- **Testy webu:** počet jazykov v prepínači sa porovnáva s počtom súborov v `locale/`.

## Obnovené z APK 0.3.0 (SHA-256 sedí so `SHA256SUMS.txt`)

- `sendspin.js` (Sendspin JS 5.0.0, hudba cez Music Assistant) a `third-party/@noble-hashes-LICENSE`.
- Originálne zvuky `alarm_beep`, `alarm`, `alarmo`, `ding`, `siren`.
- Verejný podpisový certifikát APK: `aurelvi-android/android/release-certificate.pem`
  (CN=OpenPanel Development, O=OpenPanel, C=SK, platný do 2054,
  SHA-256 `50:DA:DD:64:0B:11:15:C7:D9:67:5E:CE:54:45:7B:E8:12:05:5A:98:37:CD:C7:B3:FD:A4:6B:D6:5F:BC:2E:F0`).
  Súkromný kľúč v APK nie je. Ak nájdeš `signing/development.keystore`, over ho:
  `keytool -list -v -keystore development.keystore` musí ukázať rovnaký SHA-256 odtlačok.
