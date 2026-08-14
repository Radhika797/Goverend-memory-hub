-- Phase 10 Migration: Human Steward Tollgate Approval Cycle Fixture
-- Governed Memory Hub

DO $$
DECLARE
    v_task_id UUID := gen_random_uuid();
    v_handoff_id UUID := gen_random_uuid();
    v_approval_id UUID := gen_random_uuid();
    v_admin_id UUID;
    v_agent_id UUID;
    v_now TIMESTAMPTZ := clock_timestamp();
    v_submitted_at TIMESTAMPTZ := clock_timestamp() - INTERVAL '42 seconds';
BEGIN
    SELECT identity_id INTO v_admin_id FROM identity WHERE role = 'ADMIN' LIMIT 1;
    SELECT identity_id INTO v_agent_id FROM identity WHERE type = 'SERVICE_ACCOUNT' OR role = 'STEWARD' LIMIT 1;

    IF v_admin_id IS NULL THEN
        SELECT identity_id INTO v_admin_id FROM identity LIMIT 1;
    END IF;
    IF v_agent_id IS NULL THEN
        v_agent_id := v_admin_id;
    END IF;

    IF v_admin_id IS NOT NULL THEN
        -- Insert task
        INSERT INTO orchestration_task (task_id, initiator_identity_id, current_stage, status, created_at, updated_at)
        VALUES (v_task_id, v_admin_id, 'REQUIREMENTS_ANALYSIS', 'IN_PROGRESS', v_submitted_at, v_now)
        ON CONFLICT DO NOTHING;

        -- Insert approval (approved 42 seconds after handoff submission)
        INSERT INTO approval (approval_id, approver_id, approval_type, object_type, object_id, approved_payload_hash, policy_version, status, created_at)
        VALUES (v_approval_id, v_admin_id, 'STAGE_HANDOFF', 'governed_handoff', v_handoff_id::text, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'v1.0.0', 'APPROVED', v_now)
        ON CONFLICT DO NOTHING;

        -- Insert handoff submitted 42 seconds before approval
        INSERT INTO governed_handoff (handoff_id, task_id, stage, producer_agent_id, consumer_agent_id, proposal_payload_json, payload_hash, approval_id, status, created_at)
        VALUES (v_handoff_id, v_task_id, 'INTAKE_CLASSIFICATION', v_agent_id, v_agent_id, '{"classification":"INTERNAL"}'::jsonb, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', v_approval_id, 'APPROVED', v_submitted_at)
        ON CONFLICT DO NOTHING;
    END IF;
END $$;
