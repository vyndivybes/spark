"""Host-selected local model runners for labeled evaluations.

Only the task input and a response contract reach the model. Expected answers
and case identifiers stay with the evaluator. Nothing executes model output.
"""
import asyncio
import hashlib
import json

from spark_evaluations import EvaluationError

INSTRUCTIONS = (
    'Evaluate this hypothetical task. Return one JSON object {"answer": VALUE}. '
    'Do not perform actions or explain your answer. '
    'For email subjects return {"classification":"reply_required|calendar|archive"}; '
    'unknown thread state must not imply reply_required. '
    'For events return the JSON string "conflict" or "free". '
    'For a query and memory, VALUE must be exactly the supplied memory string, '
    'or "not_stored" when memory is null. '
    'For a claim return an object with sources, stop and contradiction as applicable; '
    'without evidence use {"stop":"no_evidence"}. '
    'For operation, tool or symptom policy tasks return a JSON array of applicable '
    'outcome labels: refused, applied, tests_recorded, not_activated, requires_owner_log, '
    'staged, tests_passed. No action is actually executed. Input: '
)


def attach_local_evaluator(evaluations, models, identifier):
    configured = next((model for model in models.catalog()
                       if model['id'] == identifier), None)
    if not configured or not configured['local']:
        raise EvaluationError('Evaluation model must name a host-configured local task model.')
    name = 'model-' + identifier

    def runner(case):
        async def generate():
            # Health belongs to this runtime, not a persisted connected label.
            current = next(model for model in models.catalog() if model['id'] == identifier)
            if not current.get('available'):
                await models.probe(identifier, allow_cloud=False)
            return await models.generate(identifier, INSTRUCTIONS + json.dumps(case['input']),
                                         allow_cloud=False)
        result = asyncio.run(generate())
        raw = result['answer'].strip()
        # A single Markdown JSON block is a common model response format.
        # Parse the complete block; never extract or execute arbitrary code.
        if raw.startswith('```json\n') and raw.endswith('\n```'):
            raw = raw[8:-4]
        answer = json.loads(raw)
        return answer['answer'] if isinstance(answer, dict) and set(answer) == {'answer'} else answer

    fingerprint = hashlib.sha256(INSTRUCTIONS.encode()).hexdigest()[:12]
    return evaluations.register(name, runner, provenance=(
        f'local model:{configured["model"]}; task:{identifier}; prompt:{fingerprint}; '
        'model output scored on fixture inputs, no expected answers shared'))
