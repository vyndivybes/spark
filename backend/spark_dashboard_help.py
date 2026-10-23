"""Grounded, read-only help for Spark's own workspace screens."""
import re


DASHBOARD_PAGES = {
    'capabilities': {
        'name': 'Capabilities',
        'location': 'Build > Capabilities',
        'purpose': 'Inspect what Spark declares it can do, compare those declarations with the current checkout, view specialist roles, and review project calculation skills.',
        'controls': [
            {'label': 'Declared capabilities and gaps', 'action': 'Shows the SAEE registry, including each capability summary, engine, approval gate, verification state, and known gaps.'},
            {'label': 'Scan this checkout', 'action': 'Checks the declared capability engines against files in the current checkout and reports missing modules, untested capability names, and exposed action sets.'},
            {'label': 'List roles', 'action': 'Lists specialist workforce roles, their responsibilities, and the actions each role may request.'},
            {'label': 'Refresh skill registry', 'action': 'Reloads calculation skills for the current project. Create or activate skills from Build > Skill forge.'},
        ],
        'safety': 'The page is read-only. Assignments and later changes still pass through their own validated dispatch and approval gates.',
        'empty_state': 'A Calculation skills count of 0 means the current project has no registered calculation skills yet.',
    },
    'missions': {
        'name': 'Missions',
        'location': 'Workspace > Missions',
        'purpose': 'Open the Autonomous Missions console to review and manage agent workloads for the current project.',
        'controls': [],
        'safety': 'Mission operations retain the workspace approval and validation rules.',
    },
    'skill forge': {'name': 'Skill forge', 'location': 'Build > Skill forge', 'purpose': 'Create, test, and activate project calculation skills.', 'controls': [], 'safety': 'Activation remains explicit.'},
    'repositories': {
        'name': 'Repositories',
        'location': 'Build > Repositories',
        'purpose': 'Learn from a local checkout or public GitHub repository and prepare reviewed improvements for Spark.',
        'controls': [
            {'label': 'Analyze repository with model', 'action': 'Uses the repository URL or path, an upgrade goal, and optional reference paths to find relevant implementation opportunities.'},
            {'label': 'Load saved analyses', 'action': 'Reloads earlier repository reports for the current project.'},
            {'label': 'Stage this opportunity', 'action': 'Creates a reviewable candidate from one selected opportunity. It does not activate the change.'},
            {'label': 'Import license and dependency evidence', 'action': 'Inspects provenance, license classification, and dependency evidence before source reuse.'},
        ],
        'workflow': ['Enter the GitHub URL or local path.', 'Describe the exact Spark improvement you want.',
                     'Analyze the repository and review the cited files and opportunities.',
                     'Import license and dependency evidence before reusing code.',
                     'Stage one opportunity, test it in Upgrade studio, inspect the diff, then approve activation separately.'],
        'safety': 'Analysis is read-only. Generated upgrades remain staged until testing, review, and explicit activation approval.',
    },
    'workbench': {'name': 'Workbench', 'location': 'Build > Workbench', 'purpose': 'Use project productivity, document, integration, and other bounded workbench actions.', 'controls': [], 'safety': 'Each action keeps its own validation and permission checks.'},
    'agent skills': {'name': 'Agent skills', 'location': 'Build > Agent skills', 'purpose': 'Review agent-oriented skills available to the current project.', 'controls': [], 'safety': 'Availability depends on the current project and configured runtime.'},
}

ALIASES = {
    'capability': 'capabilities', 'capabilities & skills': 'capabilities',
    'autonomous mission': 'missions', 'autonomous missions': 'missions', 'mission': 'missions',
    'skills': 'skill forge', 'skillforge': 'skill forge', 'repository': 'repositories',
}


def dashboard_help(page):
    if not isinstance(page, str) or not 1 <= len(page.strip()) <= 100:
        return {'ok': False, 'error': 'Name a Spark workspace screen.'}
    key = re.sub(r'\s+', ' ', page.strip().lower())
    key = re.sub(r'\s+(?:page|screen)$', '', key)
    key = re.sub(r'\s+under\s+(?:the\s+)?(?:build|workspace)$', '', key)
    key = ALIASES.get(key, key)
    match = DASHBOARD_PAGES.get(key)
    if match is None:
        return {'ok': False, 'error': 'No built-in help is recorded for that screen.',
                'known_screens': [item['name'] for item in DASHBOARD_PAGES.values()]}
    return {'ok': True, 'source': 'Spark workspace implementation', **match}
