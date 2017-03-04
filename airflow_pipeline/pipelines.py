import logging

from datetime import datetime
from textwrap import dedent

PIPELINE_XCOMS = ['folder', 'session_id', 'participant_id',
                  'scan_date', 'output', 'error', 'dataset',
                  'matlab_version', 'spm_version', 'spm_revision', 'provenance_details',
                  'provenance_previous_step_id', 'relative_context_path']


def pipeline_trigger(parent_task):
    """
      Use this function with TriggerDagRunOperator to always trigger a DAG and
      pass pipeline information to the next DAG
    """

    def trigger(context, dag_run_obj):
        """
          Use this function with TriggerDagRunOperator to always trigger a DAG and
          pass pipeline information to the next DAG
        """
        ti = context['task_instance']
        dr = context['dag_run']
        dag_run_obj.payload = {}
        for key in PIPELINE_XCOMS:
            dag_run_obj.payload[key] = ti.xcom_pull(
                task_ids=parent_task, key=key)
            if (not dag_run_obj.payload[key]) and key in dr.conf:
                dag_run_obj.payload[key] = dr.conf[key]
        return dag_run_obj

    return trigger


class TransferPipelineXComs(object):

    def __init__(self, parent_task):
        self.parent_task = parent_task
        self.pipeline_xcoms = {}
        self.incoming_parameters = dedent("""
          # Task {{ task.task_id }}
          ## Incoming parameters

          dataset = {{ task_instance.xcom_pull(task_ids='$parent_task', key='dataset') }}
          folder = {{ task_instance.xcom_pull(task_ids='$parent_task', key='folder') }}
          {% set session_id = task_instance.xcom_pull(task_ids='$parent_task', key='session_id') %}
          {% if session_id %}
          session_id = {{ session_id }}
          {% endif %}
          {% set scan_date = task_instance.xcom_pull(task_ids='$parent_task', key='scan_date') %}
          {% if scan_date %}
          scan_date = {{ scan_date }}
          {% endif %}

          {% set matlab_version = task_instance.xcom_pull(task_ids='$parent_task', key='matlab_version') %}
          {% set spm_version = task_instance.xcom_pull(task_ids='$parent_task', key='spm_version') %}
          {% set spm_revision = task_instance.xcom_pull(task_ids='$parent_task', key='spm_revision') %}
          {% set provenance_details = task_instance.xcom_pull(task_ids='$parent_task', key='provenance_details') %}
          {% if matlab_version or spm_version %}
          ## Provenance information
          matlab_version = {{ matlab_version }}
          spm_version = {{ spm_version }}
          spm_revision = {{ spm_revision }}
          provenance_details = {{ provenance_details }}

          {% endif %}
          {% set output = task_instance.xcom_pull(task_ids='$parent_task', key='output') %}
          {% set error = task_instance.xcom_pull(task_ids='$parent_task', key='error') %}
          {% if output or error %}
          ## Output from previous task $parent_task
          ### Output
          {{ output }}
          ### Errors
          {{ error }}

          {% endif %}
        """.replace("$parent_task", parent_task))

    def read_pipeline_xcoms(self, context, expected=None):
        expected = expected or []
        for xcom in PIPELINE_XCOMS:
            value = self.xcom_pull(
                context, task_ids=self.parent_task, key=xcom)
            if value:
                self.pipeline_xcoms[xcom] = value
            elif xcom in expected:
                logging.warning("xcom argument '%s' is empty", xcom)

    def write_pipeline_xcoms(self, context):
        for key, value in self.pipeline_xcoms.items():
            self.xcom_push(context, key=key, value=value)

    def trigger_dag(self, context, dag_id, output, error = ''):
        if dag_id:
            run_id = 'trig__' + datetime.now().isoformat()
            payload = {
                'output': output,
                'error': error
            }
            payload.update(self.pipeline_xcoms)

            session = settings.Session()
            dr = DagRun(
                dag_id=dag_id,
                run_id=run_id,
                conf=payload,
                external_trigger=True)
            session.add(dr)
            session.commit()
            session.close()

    def previous_step_id(self):
        id = self.pipeline_xcoms['provenance_previous_step_id']
        if id == '-1':
            return None
        else:
            return int(id)
