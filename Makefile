.PHONY: test dev run pbindlow-review pbindlow-status revgrowth-review revgrowth-status strategy-pool-overview strategy-line-allocator

dev:
	uvicorn app.main:app --reload

run:
	uvicorn app.main:app --host 127.0.0.1 --port 8000

test:
	bash scripts/test.sh

pbindlow-review:
	@test -n "$(REVIEW_ID)" || (echo "REVIEW_ID is required" && exit 1)
	@test -n "$(WINDOW_LABEL)" || (echo "WINDOW_LABEL is required" && exit 1)
	@test -n "$(START_DATE)" || (echo "START_DATE is required" && exit 1)
	@test -n "$(END_DATE)" || (echo "END_DATE is required" && exit 1)
	. .venv/bin/activate && python scripts/run_pbindlow_quarterly_review.py \
		--review-id "$(REVIEW_ID)" \
		--window-label "$(WINDOW_LABEL)" \
		--start-date "$(START_DATE)" \
		--end-date "$(END_DATE)" \
		--sample-name "$(or $(SAMPLE_NAME),expanded_main_board_1000)" \
		--sample-limit "$(or $(SAMPLE_LIMIT),1000)"

pbindlow-status:
	. .venv/bin/activate && python scripts/build_pbindlow_candidate_pool_status.py

revgrowth-review:
	@test -n "$(REVIEW_ID)" || (echo "REVIEW_ID is required" && exit 1)
	@test -n "$(WINDOW_LABEL)" || (echo "WINDOW_LABEL is required" && exit 1)
	@test -n "$(START_DATE)" || (echo "START_DATE is required" && exit 1)
	@test -n "$(END_DATE)" || (echo "END_DATE is required" && exit 1)
	. .venv/bin/activate && python scripts/run_revgrowth_quarterly_review.py \
		--review-id "$(REVIEW_ID)" \
		--window-label "$(WINDOW_LABEL)" \
		--start-date "$(START_DATE)" \
		--end-date "$(END_DATE)" \
		--sample-name "$(or $(SAMPLE_NAME),expanded_main_board_1000)" \
		--sample-limit "$(or $(SAMPLE_LIMIT),1000)"

revgrowth-status:
	. .venv/bin/activate && python scripts/build_revgrowth_candidate_pool_status.py

strategy-pool-overview:
	. .venv/bin/activate && python scripts/build_strategy_candidate_pool_overview.py

strategy-line-allocator:
	. .venv/bin/activate && python scripts/run_strategy_line_allocator.py
