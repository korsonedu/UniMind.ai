.PHONY: backend-bootstrap backend-check qa-smoke frontend-bootstrap frontend-check full-check backup

backend-bootstrap:
	bash scripts/bootstrap_backend.sh

backend-check:
	bash scripts/check_backend.sh

qa-smoke:
	bash scripts/smoke_qa.sh

frontend-bootstrap:
	bash scripts/bootstrap_frontend.sh

frontend-check:
	bash scripts/check_frontend.sh

full-check:
	bash scripts/check_all.sh

backup:
	bash scripts/backup_db.sh
