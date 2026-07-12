VISUAL_TEMPLATE_STATUS_ORDER = ["polished", "needs_review", "draft", "rework"]


VISUAL_TEMPLATE_REGISTRY = {
    "coach_trend_insight_v1": {
        "status": "polished",
        "description": "Light editorial trend card for match-by-match process charts, slopes, and readable annotations.",
        "use_for": [
            "open_play_xg_trend",
            "coach_window_trend",
            "first_vs_last_window_trend",
        ],
        "notes": "Approved from the Manchester United 33-match open-play xG trend workflow.",
        "requirements": [
            "light_theme",
            "no_overlapping_annotations",
            "clear_match_labels",
            "export_svg_and_png",
        ],
        "reference_assets": [
            "outputs/man-utd-open-play-xg-full-33-insight-v5.svg",
            "outputs/man-utd-open-play-xg-full-33-insight-v5.png",
        ],
    },
    "premium_team_compare_v1": {
        "status": "needs_review",
        "description": "Team-vs-team comparison card with WDL form and key underlying numbers.",
        "use_for": [
            "team_comparison",
            "gameweek_form",
            "head_to_head_context",
        ],
        "notes": "Useful structure, but not locked as social-ready until the next accepted revision.",
        "requirements": [
            "light_theme",
            "explicit_team_names",
            "WDL_form_visible",
            "avoid_dense_metric_blocks",
        ],
        "reference_assets": [
            "outputs/man-utd-vs-arsenal-form-v3.svg",
        ],
    },
    "process_vs_results_lens_v1": {
        "status": "needs_review",
        "description": "League-wide process-vs-results lens for xPTS gaps, finishing gaps, and defensive variance.",
        "use_for": [
            "process_vs_results",
            "xpts_overperformance",
            "variance_explainer",
        ],
        "notes": "Light-theme version exists, but needs one more visual approval pass before reuse as polished.",
        "requirements": [
            "light_theme",
            "separate_process_and_results",
            "label_variance_terms",
            "prevent_text_box_overlap",
        ],
        "reference_assets": [
            "outputs/process-vs-results-lens-light.svg",
            "outputs/process-vs-results-lens-light.png",
        ],
    },
    "player_distribution_compare_v1": {
        "status": "draft",
        "description": "Player contribution distribution card for comparing coach/team systems.",
        "use_for": [
            "player_spread",
            "chance_creation_dependency",
            "coach_player_usage",
        ],
        "notes": "Data concept is important, but visual language still needs a social-ready design pass.",
        "requirements": [
            "show_every_relevant_player",
            "rank_players_cleanly",
            "avoid_micro_labels",
            "make_dependency_story_obvious",
        ],
        "reference_assets": [
            "outputs/man-utd-amorim-vs-carrick-distribution.svg",
        ],
    },
    "prematch_matchup_v1": {
        "status": "draft",
        "description": "Prematch matchup carousel/card for team strengths, weaknesses, and storylines.",
        "use_for": [
            "prematch_preview",
            "fixture_comparison",
            "opponent_strengths",
        ],
        "notes": "Useful for Leeds-style previews, but needs clearer hierarchy before polished reuse.",
        "requirements": [
            "light_theme",
            "name_strengths_clearly",
            "carousel_copy_ready",
            "avoid_tiny_context_text",
        ],
        "reference_assets": [
            "outputs/man-utd-vs-leeds-prematch-v2.svg",
        ],
    },
    "goalkeeper_variance_v1": {
        "status": "rework",
        "description": "League goalkeeper variance card comparing xGA prevention and xPTS context.",
        "use_for": [
            "goalkeeper_variance",
            "shot_stopping_proxy",
            "keeper_vs_team_defense",
        ],
        "notes": "Data is usable, but the current visual was rejected as not good enough. Do not reuse until redesigned.",
        "requirements": [
            "light_theme",
            "large_keeper_names",
            "explain_xga_minus_ga",
            "separate_keeper_effect_from_team_defense",
            "no_crowded_league_table",
        ],
        "reference_assets": [
            "outputs/epl-goalkeeper-variance-2025.svg",
            "outputs/epl-goalkeeper-variance-2025.png",
        ],
    },
}


def get_visual_templates_by_status(status: str):
    return {
        name: metadata
        for name, metadata in VISUAL_TEMPLATE_REGISTRY.items()
        if metadata["status"] == status
    }


POLISHED_VISUAL_TEMPLATES = get_visual_templates_by_status("polished")

UNPOLISHED_VISUAL_TEMPLATES = {
    name: metadata
    for name, metadata in VISUAL_TEMPLATE_REGISTRY.items()
    if metadata["status"] != "polished"
}
