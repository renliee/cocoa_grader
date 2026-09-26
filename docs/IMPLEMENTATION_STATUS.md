# KakaoLens implementation status

Updated: 26 September 2026. The numbered acceptance ledger remains [SPEC_COMPLIANCE.md](SPEC_COMPLIANCE.md). Sections 1–82 are tracked individually; the full product is still in progress.

## Current supervised checkpoint

**Home transitions, phone photo choices, in-place History export, and branded reports are ready for operator verification.** The earlier supplier performance/profile checkpoint remains available for testing.

### Completed

- Each supplier card now opens a dedicated performance page. It shows finalized lot counts, an eligible-lot fermentation mean, chronological eligible-lot trend, range/population standard deviation when at least two eligible lots exist, and recent inspection history with a supplier-filtered History link. The page handles empty and archived suppliers. Home, History, and supplier performance now use the same current-finalized-lot query and eligibility function.
- History's **Lihat hasil** and **Ekspor laporan** actions have colored, touch-sized boxes. The report sheet aligns **Unduh laporan PDF** with the other full-width actions and places an enabled **Tampilkan kode QR** directly below it. The QR can be shown or hidden and gives LAN guidance when no reachable address is available.
- Report links use an explicit public origin when configured, otherwise the frontend request origin; the local non-Docker server discovers the active LAN interface if opened through loopback. Compose no longer forces a loopback origin. The local frontend binds to LAN by default.
- Home navigation and the header logo return to **7 Hari**. The header displays the supplied PNG at a fixed responsive aspect ratio. Green surfaces have slightly richer color, and controls/content have brief motion and feedback with reduced-motion support.
- Changing Home periods now keeps the current dashboard visible during the fetch, moves the white selection indicator smoothly, and updates the content when the response arrives. Broad content-entry animations that caused flashes were removed.
- In Sampel, **Buka kamera** uses a native rear-camera capture input. Replacing an existing photo now offers separate **Ganti dari file** and **Ambil ulang dengan kamera** controls, with the same draft-preserving upload path.
- **Ekspor laporan** on a History card opens the report sheet without navigating to the lot or sample page. Lot Detail uses the same sheet. The PDF action is vertically centered within its box.
- The supplied transparent PNG appears above the QR reveal, on the digital report and printable label, and in the PDF summary and photo pages. Existing cached PDFs regenerate on first report access using template version 2.
- Settings has a more structured profile card with account identifier, timezone, editable display name, save status, and a save button that activates when the name changes. This changes only profile presentation and the existing display-name field.
- Riwayat's primary action is **Revisi lot**. With multiple finalized lots it asks which lot to revise; each completed card also has a direct Revisi lot action. After confirmation the same lot opens at **2 · Sampel**.
- A lot has one revision draft at a time. Reopening it returns the same draft ID. It copies saved photo/precheck references without overwriting the finalized result. Add, replace, delete, clear, and classify work on that draft. Shared photos and prechecks survive draft changes and deletion.
- Finalization creates **Revisi N** on the same lot. Previous revisions remain viewable. A confirmed **Jadikan Revisi Aktif** changes the pointer only; current Home/History values use that revision. Version checks reject stale switches or finalization after its base revision stops being active.
- Riwayat and finalized Lot Detail expose **Ekspor laporan / Bagikan / Ekspor Laporan**. A report has one stable, unguessable token tied to one finalized revision. It freezes supplier/lot identity and measured evidence.
- Public read-only digital report includes identity, weight when known, date/revision, bean counts, sample warning, fermentation composition, exclusion breakdown, every final annotated image and a scope limitation. It works without an account.
- PDF export runs in a persisted queued/running/failed/complete job, supports retry, caches the file and includes all annotated images with per-photo captions. QR encodes the effective absolute digital URL. A simple printable label is available with a LAN/public URL.
- Report and public asset URLs are kept out of the app's usual access logs where practical. Public token access cannot read private unrelated images.

### Verification

- `.venv\Scripts\python -m unittest discover -s backend/tests -v`: **10 passed**, including LAN/public origin selection, real QR decoding, and supplier performance/owner isolation.
- `node --test frontend/tests/*.mjs`: **6 passed**, including the new direct supplier-performance route.
- `node --check` on changed views and `python -m compileall -q backend frontend/serve.py` passed; `git diff --check` found no whitespace errors.
- Restarted local frontend/backend. `http://10.5.143.184:8081/`, `/assets/logo.png`, and proxied `/api/health` each returned HTTP 200 from the active Wi-Fi address. A live existing report QR decoded to the same LAN report URL, and that public page returned HTTP 200.
- Generated a branded PDF from an existing report snapshot and visually inspected its summary and annotated-image pages. After restarting the backend, an existing report regenerated to template version 2, downloaded, and contained the logo image.
- Browser automation was unavailable in this environment, so phone-width layout, camera capture, and QR scanning remain operator checks.
- The prior report checkpoint decoded its QR against the configured LAN URL and visually inspected a representative PDF summary/image page. The new controls still need operator phone review.

### Known limitations

- Supplier performance presents the five most recent inspections and links to supplier-filtered History for the full ordinary list. History's advanced date/band/governance filters are still pending. Password change and broader Settings work were outside this profile-only revision.
- Full 1–82 specification is still incomplete. Governance flags, manual exclusion, lot archive/delete, linked supplier deletion, advanced History filters, supplier analytics/comparison, and earlier photo review gaps remain tracked in the numbered ledger.
- No physical phone camera or two-device LAN test was possible in the tool environment. Native file capture depends on the phone browser/OS. PDF export of a full 50-photo lot is supported by the one-image-per-page implementation but has not been visually inspected as a 51-page document.
- Automatic LAN selection follows the active network route; multi-interface systems can override it with `KAKAO_PUBLIC_BASE_URL`. Phone access still depends on the Wi-Fi allowing device-to-device traffic and the host firewall allowing the frontend port.
- The local backend and frontend were restarted after this change. Refresh the browser with Ctrl+F5.
- Report export was advanced ahead of the unfinished governance/analytics work because this checkpoint was explicitly requested. Its snapshot binds directly to an immutable finalized revision and does not depend on those later screens.

## Plan phase ledger

| Phase | State | Progress |
| --- | --- | --- |
| 0 — Review | Complete | Both planning documents and MVP code reviewed. |
| 1 — Foundation | In Progress | SQLite/auth/required suppliers/owner isolation work; linked supplier deletion remains. |
| 2 — Precheck | In Progress | Authoritative persisted evidence and separate file/camera replacement choices work; explicit photo acceptance/detail review gaps remain. |
| 3 — Analysis/finalization | In Progress | Real CV, drafts, same-lot revision finalization; result exclusion detail remains. |
| 4 — Revision/governance | In Progress | Working copies, immutable history, current pointer are implemented; governance/archive/delete remain. |
| 5 — Analytics/comparison | In Progress | Home and supplier performance use shared current/eligible lot data; comparison and advanced filters remain. |
| 6 — Reports/LAN | In Progress | Digital/PDF/QR/label, in-place History export, branded PDF v2 and automatic LAN origin implemented; physical LAN phone demonstration pending. |
| 7 — Demo/recovery | In Progress | Startup docs and guide exist; seed/recovery release tasks remain. |

## Please manually test

1. Open `http://10.5.143.184:8081` on a phone on the same Wi-Fi and refresh the laptop page with Ctrl+F5. On Home, switch **7 Hari → 30 Hari → 3 Bulan**; confirm the old dashboard stays visible during loading, the white selection slides smoothly, and no full-page flash occurs. Leave Home and return; confirm **7 Hari**.
2. In **2 · Sampel**, tap **Buka kamera** and take a photo. On an existing photo, use both **Ganti dari file** and **Ambil ulang dengan kamera**. Confirm the chosen photo appears, precheck reruns, and a canceled picker leaves the prior photo intact.
3. In **Riwayat → Selesai**, tap **Ekspor laporan**. Confirm the URL stays on Riwayat, the PDF button text is centered, and closing the sheet returns to the same History list. Download the PDF and check both summary and photo pages for the new logo.
4. Reveal the QR and check its new logo above the code. Scan the code from the phone and confirm the public report and annotated images open without login; open the printable label and check its logo. If the phone cannot open the LAN URL, check the firewall or Wi-Fi isolation.
5. In **Pemasok**, tap **Lihat Performa** on suppliers with and without finalized lots. In **Pengaturan**, edit/save the display name and refresh to confirm persistence.

## Next

## English interface and centered report modal — Complete (operator review pending)

- Centered the Share / Export Report dialog on desktop and phone viewports, including the heading, description, URL/copy section, PDF/QR actions, logo, and QR. Compact spacing, consistent touch targets, internal scrolling, and reduced-motion support remain in place.
- Translated application navigation, forms, loading/error messages, guidance, results, public reports, PDF captions, and the legacy MVP into English. Preserved SNI terminology, proper names, user content, API field names, numerical rules, and CV processing.
- Saved evidence receives English system labels at the presentation boundary. Frozen data and original annotated images are retained. PDF template v3 refreshes older cached exports without rerunning analysis.
- Verification: 10 existing backend tests and 6 frontend tests passed; 3 new presentation tests passed (immutable data/user text, legacy warnings, empty prechecks). Python compilation, all frontend JS syntax checks, legacy inline-script syntax, and diff whitespace checks passed. Visually inspected an English PDF summary. Restarted backend and downloaded a live 4-page English PDF; health returned 200.
- Manual checkpoint: refresh with Ctrl+F5; open History → Export report; check centering at desktop and phone widths, copy the link, reveal/hide QR, download PDF, and close the modal while remaining in History. Review English text in Suppliers, Settings, Sample, Results, and public report.
- Limitations: browser layout and physical phone scanning still require operator verification. Previously saved raster evidence and diagnostic error records retain their original contents. No schema or ML algorithm changes.

After this operator checkpoint, close the still-open numbered photo review requirements, then finish governance/deletion and the remaining analytics/comparison work.
