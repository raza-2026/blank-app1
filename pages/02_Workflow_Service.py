
# pages/02_Workflow_Service.py
import json
import time
import streamlit as st

from osdu_app.config import load_config
from osdu_app.auth import get_access_token
from osdu_app.workflow_service import WorkflowService


def main():
    st.set_page_config(page_title="Workflow Service (Phase 2)", layout="wide")
    st.title("Workflow Service • Module (Phase 2)")
    st.caption(
        "This module demonstrates Workflow Service discovery, workflow details, run history, run status, and run update operations."
    )

    cfg = load_config()

    def get_wf_api() -> WorkflowService:
        token = get_access_token(cfg)
        return WorkflowService(cfg, token)

    # -------------------------
    # 1) Service Info
    # -------------------------
    with st.expander("Workflow Service Info (/info)", expanded=False):
        if st.button("Get /info", key="wf_info_btn"):
            try:
                wf = get_wf_api()
                data, meta = wf.info(return_meta=True)
                st.subheader("Request Meta")
                st.json(meta)
                st.subheader("Response")
                st.json(data)
            except Exception as e:
                st.exception(e)

    # -------------------------
    # 2) List workflows + details
    # -------------------------
    with st.expander("List Workflows + Details", expanded=True):
        col1, col2 = st.columns([1, 2])

        with col1:
            prefix = st.text_input("Filter prefix (optional)", value="", key="wf_prefix")

            # ✅ Button key is wf_list_btn (NOT wf_list)
            if st.button("List workflows", key="wf_list_btn"):
                try:
                    wf = get_wf_api()
                    items, raw, meta = wf.list_workflows(prefix=prefix or None, return_meta=True)

                    # ✅ Store results in non-widget keys
                    st.session_state["wf_workflows_items"] = items
                    st.session_state["wf_workflows_raw"] = raw
                    st.session_state["wf_workflows_meta"] = meta

                    st.success(f"Normalized workflows count: {len(items)}")
                except Exception as e:
                    st.exception(e)

            workflows = st.session_state.get("wf_workflows_items", [])
            raw_workflows = st.session_state.get("wf_workflows_raw", None)
            meta = st.session_state.get("wf_workflows_meta", None)

            if not isinstance(workflows, list):
                st.warning(f"Unexpected workflows type: {type(workflows)}. Resetting to empty list.")
                workflows = []

            if len(workflows) == 0:
                st.info("No workflows returned (or response format differs). Debug below:")
                if meta is not None:
                    st.subheader("Request Meta")
                    st.json(meta)
                if raw_workflows is not None:
                    st.subheader("Raw Response")
                    st.json(raw_workflows)

            # Build list for dropdown
            names = []
            for w in workflows:
                if isinstance(w, dict):
                    names.append(w.get("workflowName") or w.get("name") or w.get("workflowId") or str(w))
                else:
                    names.append(str(w))

            selected = st.selectbox(
                "Select a workflow",
                options=[""] + names,
                index=0,
                key="wf_selected",   # OK: widget key
            )

        with col2:
            if selected:
                st.subheader("Workflow Details")
                try:
                    wf = get_wf_api()
                    details, meta = wf.get_workflow(selected, return_meta=True)
                    st.subheader("Request Meta")
                    st.json(meta)
                    st.subheader("Response")
                    st.json(details)
                except Exception as e:
                    st.exception(e)
            else:
                st.info("Select a workflow to view details.")

    # -------------------------
    # 3) Run history (list runs)
    # -------------------------
    with st.expander("Workflow Run History (GET /workflow/{name}/workflowRun)", expanded=False):
        workflow_name = st.text_input("Workflow name", value=cfg.workflow_name, key="wf_runs_name")

        st.caption("Some deployments require query param `params`. Try {} or leave blank if it fails.")
        params_text = st.text_area("params (optional JSON object)", value="{}", height=100, key="wf_runs_params")

        if st.button("List runs", key="wf_list_runs_btn"):
            try:
                params_obj = None
                if params_text.strip():
                    params_obj = json.loads(params_text)

                wf = get_wf_api()
                runs, raw, meta = wf.list_runs(workflow_name, params_obj=params_obj, return_meta=True)

                st.session_state["wf_runs_items"] = runs
                st.session_state["wf_runs_raw"] = raw
                st.session_state["wf_runs_meta"] = meta

                st.success(f"Normalized runs count: {len(runs)}")

            except Exception as e:
                st.exception(e)

        runs = st.session_state.get("wf_runs_items", [])
        raw_runs = st.session_state.get("wf_runs_raw", None)
        runs_meta = st.session_state.get("wf_runs_meta", None)

        if not isinstance(runs, list):
            st.warning(f"Unexpected runs type: {type(runs)}. Resetting to empty list.")
            runs = []

        if len(runs) == 0 and (raw_runs is not None or runs_meta is not None):
            st.info("No runs returned. Debug below:")
            if runs_meta is not None:
                st.subheader("Request Meta")
                st.json(runs_meta)
            if raw_runs is not None:
                st.subheader("Raw Response")
                st.json(raw_runs)

        if isinstance(runs, list) and runs and isinstance(runs[0], dict):
            compact = []
            for r in runs:
                compact.append(
                    {
                        "runId": r.get("runId"),
                        "status": r.get("status"),
                        "workflowName": r.get("workflowName") or r.get("workflowId"),
                        "submittedBy": r.get("submittedBy"),
                        "startTimeStamp": r.get("startTimeStamp"),
                        "endTimeStamp": r.get("endTimeStamp"),
                    }
                )
            st.dataframe(compact, use_container_width=True)
        elif runs:
            st.json(runs)

    # -------------------------
    # 4) Run status + polling
    # -------------------------
    with st.expander("Workflow Run Status (GET /workflow/{name}/workflowRun/{runId})", expanded=True):
        col1, col2 = st.columns([1, 1])

        with col1:
            wf_name = st.text_input("Workflow name", value=cfg.workflow_name, key="wf_status_name")
            run_id = st.text_input("runId", value="", key="wf_status_runid")
            poll = st.checkbox("Poll every 5s (max 60 times)", value=False, key="wf_poll")

            if st.button("Get status", key="wf_get_status_btn"):
                try:
                    wf = get_wf_api()
                    status = wf.status(wf_name, run_id)
                    st.session_state["wf_last_status_obj"] = status
                except Exception as e:
                    st.exception(e)

        with col2:
            status_obj = st.session_state.get("wf_last_status_obj")
            if status_obj:
                st.subheader("Latest Status Response")
                st.json(status_obj)

        if poll and wf_name and run_id:
            st.info("Polling...")
            for _ in range(60):
                try:
                    wf = get_wf_api()
                    status = wf.status(wf_name, run_id)
                    st.session_state["wf_last_status_obj"] = status

                    st.write("status:", status.get("status", status))

                    if status.get("status") in ("finished", "completed", "success", "failed", "error"):
                        st.success("Terminal status reached.")
                        st.json(status)
                        break

                except Exception as e:
                    st.exception(e)
                    break

                time.sleep(5)

    # -------------------------
    # 5) Update run
    # -------------------------
    with st.expander("Update Workflow Run (PUT /workflow/{name}/workflowRun/{runId})", expanded=False):
        wf_name = st.text_input("Workflow name", value=cfg.workflow_name, key="wf_update_name")
        run_id = st.text_input("runId", value="", key="wf_update_runid")
        status = st.selectbox(
            "Set status to",
            options=["submitted", "running", "finished", "failed", "success", "queued"],
            index=3,
            key="wf_update_status",
        )

        if st.button("Update run", key="wf_update_btn"):
            try:
                wf = get_wf_api()
                resp = wf.update_run(wf_name, run_id, status)
                st.json(resp)
                st.success("Update run request sent.")
            except Exception as e:
                st.exception(e)


if __name__ == "__main__":
    main()
