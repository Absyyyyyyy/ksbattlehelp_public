from __future__ import annotations
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import streamlit as st

try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
except Exception:
    add_script_run_ctx = None
    get_script_run_ctx = None

from kingshot_sim.optimizer.best_counter import SearchCancelled
from kingshot_sim.webui import runtime_stats
from kingshot_sim.io_pkg import scope


MAX_SEARCH_SIZE = 1_500_000


@dataclass
class SearchJob:
    phase: str = "idle"
    progress_done: int = 0
    progress_total: int = 0
    progress_text: str = "Starting..."
    cancel_event: threading.Event = field(default_factory=threading.Event)
    result_status: str = ""
    result_payload: Any = None
    started_at: float = 0.0


@st.cache_resource
def _global_search_lock() -> threading.Lock:
    return threading.Lock()


def start_search(
    job: SearchJob,
    work_fn: Callable[..., Any],
    work_kwargs: dict,
    n_total: int,
) -> None:
    lock = _global_search_lock()

    job.phase = "queued"
    job.progress_done = 0
    job.progress_total = max(int(n_total), 0)
    job.progress_text = "Waiting in queue..."
    job.cancel_event = threading.Event()
    job.result_status = ""
    job.result_payload = None
    job.started_at = time.time()

    def _worker() -> None:
        acquired = False
        scope.mark_no_session_storage()
        runtime_stats.queue_enter()
        running_counted = False
        try:
            while True:
                if job.cancel_event.is_set():
                    job.result_status = "cancelled"
                    runtime_stats.queue_exit_unstarted()
                    return
                acquired = lock.acquire(timeout=0.25)
                if acquired:
                    break

            runtime_stats.queue_to_running()
            running_counted = True
            job.phase = "running"
            job.progress_text = "Starting..."

            def _progress_cb(done: int, total: int) -> None:
                job.progress_done = int(done)
                if total > 0:
                    job.progress_total = int(total)
                    if done >= total:
                        job.progress_text = (
                            f"Refining top candidates "
                            f"(this is the last step)…"
                        )
                    else:
                        job.progress_text = (
                            f"Testing compositions: {done:,} / {total:,}"
                        )
                if job.cancel_event.is_set():
                    raise SearchCancelled()

            report = work_fn(progress=_progress_cb, **work_kwargs)
            if getattr(report, "cancelled", False):
                job.result_status = "cancelled"
                job.result_payload = report
            else:
                job.result_status = "ok"
                job.result_payload = report
                try:
                    runtime_stats.increment_total_sims()
                    runtime_stats.add_total_battles(getattr(report, "n_battles", 0))
                except Exception:
                    pass
        except SearchCancelled:
            job.result_status = "cancelled"
        except Exception as e:
            job.result_status = "error"
            job.result_payload = repr(e)
        finally:
            if acquired:
                try:
                    lock.release()
                except RuntimeError:
                    pass
            if running_counted:
                runtime_stats.queue_exit_running()
            scope.clear_no_session_storage()
            job.phase = "done"

    t = threading.Thread(target=_worker, daemon=True, name="kingshot-search")
    if add_script_run_ctx is not None and get_script_run_ctx is not None:
        try:
            ctx = get_script_run_ctx()
            if ctx is not None:
                add_script_run_ctx(t, ctx)
        except Exception:
            pass
    t.start()


def render_running_panel(
    job: SearchJob,
    *,
    cancel_key: str,
    poll_interval: float = 1.0,
) -> None:
    @st.fragment(run_every=poll_interval)
    def _live_panel() -> None:
        if job.phase not in ("queued", "running"):
            st.rerun(scope="app")
            return

        if job.phase == "queued":
            q = runtime_stats.get_queue_count()
            r = runtime_stats.get_running_count()
            ahead = max(0, q - 1) + max(0, r)
            if ahead <= 0:
                st.info(
                    "**Queued**. Another search is running on the "
                    "server. Yours will start as soon as it finishes."
                )
            else:
                eta_min = ahead
                noun = "sim" if ahead == 1 else "sims"
                st.info(
                    f"**Queued**. **{ahead}** {noun} ahead of you · "
                    f"approx. **~{eta_min} min** wait. Yours starts "
                    f"automatically when the lock frees."
                )

        total = max(int(job.progress_total), 1)
        done = max(0, min(int(job.progress_done), total))
        pct = max(0.0, min(1.0, done / total))
        st.progress(pct, text=job.progress_text or "Working...")

        c1, c2 = st.columns([1, 3])
        with c1:
            if not job.cancel_event.is_set():
                if st.button(
                    "⏹ Cancel", key=cancel_key, use_container_width=True
                ):
                    job.cancel_event.set()
                    st.rerun(scope="fragment")
            else:
                st.caption("Cancelling. Please wait...")
        with c2:
            elapsed = (
                time.time() - job.started_at if job.started_at else 0.0
            )
            st.caption(f"⏱ Elapsed: {elapsed:.1f}s")

    _live_panel()


__all__ = [
    "SearchJob",
    "start_search",
    "render_running_panel",
    "MAX_SEARCH_SIZE",
]
