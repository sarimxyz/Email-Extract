def after_install(app=None, **kwargs):
	"""
	Run prompt backfill right after app installation.

	This complements Frappe migrations/patches, which only run once per site
	based on patch history.
	"""
	# Import inside the hook to avoid import-time issues during app bootstrapping.
	from fab_cars.patches.ensure_prompt_placeholder import execute

	# `execute()` does its own db commit.
	execute()
