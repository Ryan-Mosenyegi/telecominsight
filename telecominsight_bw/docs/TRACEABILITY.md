## Addendum: multi-provider access control and deployment

Added after the original catalogue. Provider users sign in on `app.py`, upload their own data and see
only their own records. Administrators sign in on `admin_app.py` and manage accounts and access.

| Req ID | Requirement | Implemented in | Verified by |
|---|---|---|---|
| NEW | Providers and users can be created, enabled, disabled; passwords can be reset | `admin_ui._accounts_tab`, `db.create_provider`, `db.create_user`, `db.set_provider_status`, `db.set_user_active`, `db.set_password_hash` | `test_disabled_user_cannot_sign_in`, `test_disabled_provider_blocks_its_users_only`, `test_password_reset_replaces_the_old_password` |
| NEW | Passwords stored only as salted scrypt hashes; failed sign-in never reveals whether a username exists | `auth.hash_password`, `auth.verify_password`, `auth.authenticate` | `test_wrong_password_and_unknown_user_get_the_same_message`, `test_user_listing_never_exposes_password_hashes` |
| NEW | Sessions expire after 60 minutes | `auth.new_session`, `auth.is_expired`, `login_ui.require_login` | Manual check (no automated test) |
| NEW | Accounts lock for 15 minutes after 5 failed sign-ins | `login_ui.show_login_page`, `db.recent_failed_logins` | `test_failed_logins_are_counted_per_user` (counting); lockout message checked manually |
| NEW | Disabling a user or provider takes effect on the next page load | `db.is_account_active`, `login_ui.require_login` | `test_disabled_user_is_not_active`, `test_disabled_provider_makes_its_users_inactive`, `test_unknown_user_is_not_active` |
| NEW | A provider user sees only their own provider's records, charts, reports and exports | `db.load_records(engine, provider_id)`, `app.load_data` (cache keyed by provider id) | `test_provider_only_gets_own_rows`, `test_provider_match_ignores_capitals`, `test_unknown_provider_id_gets_nothing`, `test_load_records_cannot_be_called_without_a_provider`, `test_analysis_on_scoped_data_contains_only_that_provider`, `test_provider_sees_the_dashboard_on_the_provider_site` |
| NEW | Providers upload their own CSV; rows naming another provider are rejected | `upload_ui.render`, `db.save_provider_records` | `test_upload_saves_only_the_providers_own_rows`, `test_upload_cannot_target_an_unknown_provider`, `test_upload_of_only_foreign_rows_saves_nothing`, `test_uploading_the_same_file_twice_skips_duplicates` |
| NEW | A provider sees only their own upload history | `db.list_provider_uploads` | `test_upload_history_is_private_to_each_provider` |
| NEW | A provider can remove their own fictional demo data without affecting others | `upload_ui.render`, `db.count_provider_source`, `db.delete_provider_source` | `test_removing_demo_data_only_touches_own_provider` |
| NEW | Provider and administrator use separate sites and each refuses the other's accounts | `app.py`, `admin_app.py`, `login_ui.require_login` | `test_admin_account_is_turned_away_from_the_provider_site`, `test_provider_account_is_turned_away_from_the_admin_site`, `test_admin_sees_admin_tabs_and_no_dashboard_on_the_admin_site`, `test_signed_out_visitors_see_only_the_login_form_on_both_sites` |
| NEW | Administrator sees record counts per provider, all upload batches, and can remove demo data, but never provider rows or analytics | `admin_ui._data_tab`, `db.record_counts_by_provider`, `db.list_batches`, `db.count_source`, `db.delete_source` | `test_counts_and_demo_removal`, `test_list_batches_shows_every_upload` |
| NEW | Sign-ins, failures, uploads and admin actions are written to an access log the administrator can read | `db.log_event`, `db.recent_access_log`, `admin_ui` (Access log tab) | `test_failed_login_is_logged` |
| NEW | The first administrator can be created from environment variables on a server | `bootstrap.ensure_admin`, `db.admin_exists` | `test_bootstrap_creates_admin_once`, `test_bootstrap_does_nothing_without_settings`, `test_bootstrap_rejects_a_short_password` |
| NEW | Demo data seeding can be switched off for real deployments | `config.seed_demo_enabled`, `db.seed_if_empty` | `test_seed_switch` |
| NEW (NFR) | Deployable with Docker and PostgreSQL; secrets via environment; HTTPS via reverse proxy | `Dockerfile`, `docker-compose.yml`, `.env.example`, `.streamlit/config.toml`, `docs/DEPLOYMENT.md` | Manual: "Before going live" checklist in `docs/DEPLOYMENT.md` |

### Existing requirements whose implementation changed

Review these rows in the main table. I haven't seen them, so treat this as a checklist:

- **Upload and save (FR01, FR02, FR12 and NFR04 per your Figure 1 text):** the actor is now a provider user, not the administrator. The code path is `upload_ui` then `db.save_provider_records`, which calls `db.save_records`. The `ADMIN_PASSWORD` check no longer exists.
- **Dashboard loading (FR03):** records load per provider through `db.load_records(engine, provider_id)`, and the cached `load_data` takes a provider id.
- **Provider comparison chart (within FR05 to FR11):** removed, because a provider's data now contains only that provider. The Providers section of the PDF report (FR10) now has a single row.
- **Cleaning (FR04, NFR02):** unchanged, but a new rule applies after it: rows whose provider is not the uploader's are rejected.
- **Demo data seeding:** now optional through `SEED_DEMO_DATA`.

### Known gaps

- Session expiry and the lockout message are checked by hand, not by automated tests.
- `tests/test_app_roles.py` and the new tests have not been run by me. Record the real pass/fail result here once you've run `python -m pytest -v`.