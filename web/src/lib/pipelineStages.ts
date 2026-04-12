/**
 * 8-stage pipeline in default order. Zones group stages per spec §3.
 * Zone layout drives the React Flow node positions.
 */

export const STAGE_SEQUENCE = [
  "literature_review",
  "plan_formulation",
  "data_exploration",
  "data_preparation",
  "experimentation",
  "results_interpretation",
  "report_writing",
  "peer_review",
] as const;

export type Stage = (typeof STAGE_SEQUENCE)[number];

export const STAGE_LABELS: Record<Stage, string> = {
  literature_review: "Literature Review",
  plan_formulation: "Plan Formulation",
  data_exploration: "Data Exploration",
  data_preparation: "Data Preparation",
  experimentation: "Experimentation",
  results_interpretation: "Results Interpretation",
  report_writing: "Report Writing",
  peer_review: "Peer Review",
};

export type Zone = "Discovery" | "Implementation" | "Synthesis";

export const STAGE_ZONE: Record<Stage, Zone> = {
  literature_review: "Discovery",
  plan_formulation: "Discovery",
  data_exploration: "Implementation",
  data_preparation: "Implementation",
  experimentation: "Implementation",
  results_interpretation: "Synthesis",
  report_writing: "Synthesis",
  peer_review: "Synthesis",
};

export const ZONE_X: Record<Zone, number> = {
  Discovery: 80,
  Implementation: 380,
  Synthesis: 680,
};

/**
 * Returns x/y coordinates for each stage. Zones flow left-to-right;
 * within a zone, stages stack vertically.
 */
export function stagePositions(): Record<Stage, { x: number; y: number }> {
  const positions = {} as Record<Stage, { x: number; y: number }>;
  const zoneCounters: Record<Zone, number> = {
    Discovery: 0,
    Implementation: 0,
    Synthesis: 0,
  };
  for (const stage of STAGE_SEQUENCE) {
    const zone = STAGE_ZONE[stage];
    positions[stage] = {
      x: ZONE_X[zone],
      y: 80 + zoneCounters[zone] * 100,
    };
    zoneCounters[zone] += 1;
  }
  return positions;
}
