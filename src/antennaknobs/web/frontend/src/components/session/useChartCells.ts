import type { MutableRefObject } from "react";
import type { SolveRequest } from "../../lib/api";
import type { BackendEntry } from "../../lib/backends";
import type { ParamSweepRequest } from "../../lib/paramSweep";
import type { SweepProjectionSet } from "../../lib/refine";
import type { SweepRange } from "../../lib/sweep";
import type { SweepAxes } from "../../lib/sweepAxis";
import {
  type ChartCellRequest,
  freqSweepSignature,
  NOT_APPROVED,
  paramSweepSignature,
} from "./useAnalysisRunners";
import { type FreqSweepHandle, useFreqSweep } from "./useFreqSweep";
import { type ParamSweepHandle, useParamSweep } from "./useParamSweep";

// The runners behind an analysis chart's curves (AK#1757, sweep-framework
// step 5 unit 4): one frequency sweep runner and one parameter sweep runner
// per engine x ground cell, up to the curve cap. React's hooks cannot be
// called a variable number of times, so this holds a FIXED six pairs
// (lib/chartCells.ts CURVE_CAP), unrolled, and the cells the chart has not
// got are idle: not wanted, so they run nothing and hold nothing.
//
// Each curve is exactly the single-curve chart's runner pair on that cell's
// request (`build`: the cell's slot and ground slot, DesignSession's
// buildCellRequest), keyed on that request's own signature, so a curve
// re-sweeps when its own slot or ground changes and not otherwise.

/** What one curve runs: its cell and the chart's run inputs (the same for
 *  every curve of a chart, lib/analysisChart.ts chartRunInputs). */
export type CellRun = {
  cell: ChartCellRequest;
  freq: {
    range: SweepRange;
    wanted: boolean;
    auto: boolean;
    views: SweepProjectionSet;
  };
  param: { req: ParamSweepRequest; wanted: boolean };
};

export type CellRunners = { freq: FreqSweepHandle; param: ParamSweepHandle };

/** The number of runner pairs one chart holds: the curve cap. */
export const CELL_RUNNERS = 6;

const NO_VIEWS: SweepProjectionSet = { vswr: false, gamma: false, smith: false };

export type ChartCellsOptions = {
  /** This chart's curves, in cell order: at most CELL_RUNNERS. */
  runs: readonly CellRun[];
  /** Any valid run, only to fill the idle pairs' inputs. */
  idle: CellRun;
  /** A cell's solve request. */
  build: (cell: ChartCellRequest) => SolveRequest;
  refineEnabled: boolean;
  z0: number;
  sweepAxes: SweepAxes;
  swrThreshold: number;
  autoSim: boolean;
  active: boolean;
  comboApproved: boolean;
  recommendedBackend: BackendEntry | null;
  solveWithheld: () => boolean;
  seqRef: MutableRefObject<number>;
  /** The session's "Solve anyway", for the curves on the active slot. */
  approvedComboRef: MutableRefObject<boolean>;
};

export function useChartCells(o: ChartCellsOptions): CellRunners[] {
  const { build, approvedComboRef } = o;
  const freqOptions = (run: CellRun | undefined) => {
    const r = run ?? o.idle;
    const on = run !== undefined;
    return {
      range: r.freq.range,
      sig: on ? freqSweepSignature(build(r.cell)) : "",
      enabled: on && r.freq.wanted,
      resident: on && r.freq.wanted,
      auto: r.freq.auto,
      backend: r.cell.backend,
      groundEnabled: r.cell.groundEnabled,
      groundModel: r.cell.groundModel,
      refineEnabled: o.refineEnabled,
      z0: o.z0,
      residentSweepViews: on ? r.freq.views : NO_VIEWS,
      sweepAxes: o.sweepAxes,
      swrThreshold: o.swrThreshold,
      autoSim: o.autoSim,
      active: o.active,
      comboApproved: o.comboApproved,
      recommendedBackend: o.recommendedBackend,
      buildRequest: () => build(r.cell),
      solveWithheld: o.solveWithheld,
      seqRef: o.seqRef,
      approvedComboRef: r.cell.onActiveSlot ? approvedComboRef : NOT_APPROVED,
    };
  };
  const paramOptions = (run: CellRun | undefined) => {
    const r = run ?? o.idle;
    const on = run !== undefined;
    return {
      req: r.param.req,
      sig: on ? paramSweepSignature(build(r.cell), r.param.req) : "",
      wanted: on && r.param.wanted,
      autoSim: o.autoSim,
      active: o.active,
      comboApproved: o.comboApproved,
      recommendedBackend: o.recommendedBackend,
      buildRequest: () => build(r.cell),
      solveWithheld: o.solveWithheld,
      seqRef: o.seqRef,
      approvedComboRef: r.cell.onActiveSlot ? approvedComboRef : NOT_APPROVED,
    };
  };
  const f0 = useFreqSweep(freqOptions(o.runs[0]));
  const p0 = useParamSweep(paramOptions(o.runs[0]));
  const f1 = useFreqSweep(freqOptions(o.runs[1]));
  const p1 = useParamSweep(paramOptions(o.runs[1]));
  const f2 = useFreqSweep(freqOptions(o.runs[2]));
  const p2 = useParamSweep(paramOptions(o.runs[2]));
  const f3 = useFreqSweep(freqOptions(o.runs[3]));
  const p3 = useParamSweep(paramOptions(o.runs[3]));
  const f4 = useFreqSweep(freqOptions(o.runs[4]));
  const p4 = useParamSweep(paramOptions(o.runs[4]));
  const f5 = useFreqSweep(freqOptions(o.runs[5]));
  const p5 = useParamSweep(paramOptions(o.runs[5]));
  return [
    { freq: f0, param: p0 },
    { freq: f1, param: p1 },
    { freq: f2, param: p2 },
    { freq: f3, param: p3 },
    { freq: f4, param: p4 },
    { freq: f5, param: p5 },
  ];
}
