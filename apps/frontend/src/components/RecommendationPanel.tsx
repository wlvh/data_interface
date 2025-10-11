import { useEffect, useMemo, useState } from "react";
import { useAppDispatch, useAppSelector } from "@/hooks/storeHooks";
import { selectRecommendationState, selectSelectedCandidateId, selectRecommendationStatus, selectRecommendationError, refreshRecommendations, selectCandidate } from "@/app/recommendationSlice";
import { selectTaskIdentifiers, selectPlan, selectOutputTable } from "@/app/taskSlice";
import { selectChartSpec, applyChartPatch } from "@/app/chartSlice";
import { runNaturalEdit } from "@/app/naturalEditSlice";
import { buildCandidateAdoptionPatch } from "@/utils/patch";

export interface RecommendationPanelProps {
  onCommandSample: (command: string) => void;
}

export default function RecommendationPanel({ onCommandSample }: RecommendationPanelProps) {
  const dispatch = useAppDispatch();
  const recommendations = useAppSelector(selectRecommendationState);
  const selectedCandidateId = useAppSelector(selectSelectedCandidateId);
  const status = useAppSelector(selectRecommendationStatus);
  const error = useAppSelector(selectRecommendationError);
  const { taskId, datasetId } = useAppSelector(selectTaskIdentifiers);
  const plan = useAppSelector(selectPlan);
  const outputTable = useAppSelector(selectOutputTable);
  const chartSpec = useAppSelector(selectChartSpec);

  const [viewMode, setViewMode] = useState<"carousel" | "gallery">("carousel");
  const [carouselIndex, setCarouselIndex] = useState(0);

  const candidates = recommendations?.recommendations ?? [];

  useEffect(() => {
    setCarouselIndex(0);
  }, [recommendations]);

  useEffect(() => {
    if (selectedCandidateId) {
      const index = candidates.findIndex((candidate) => candidate.candidate_id === selectedCandidateId);
      if (index >= 0) {
        setCarouselIndex(index);
      }
    }
  }, [selectedCandidateId, candidates]);

  const currentCandidate = useMemo(() => candidates[carouselIndex], [candidates, carouselIndex]);

  const handleRefresh = () => {
    if (!taskId || !datasetId || !plan || !outputTable) {
      return;
    }
    dispatch(
      refreshRecommendations({
        taskId,
        datasetId,
        plan,
        tableId: outputTable.output_table_id,
      }),
    );
  };

  const handleSurprise = () => {
    if (!taskId || !datasetId || !chartSpec || !recommendations || recommendations.surprise_pool.length === 0) {
      return;
    }
    const randomIndex = Math.floor(Math.random() * recommendations.surprise_pool.length);
    const command = recommendations.surprise_pool[randomIndex];
    onCommandSample(command);
    dispatch(
      runNaturalEdit({
        taskId,
        datasetId,
        chartSpec,
        command,
      }),
    );
  };

  const adoptCandidate = (candidateId: string) => {
    if (!taskId || !datasetId || !chartSpec || !recommendations) {
      return;
    }
    const candidate = candidates.find((item) => item.candidate_id === candidateId);
    if (!candidate) {
      return;
    }
    const patch = buildCandidateAdoptionPatch({
      currentChartId: chartSpec.chart_id,
      candidate: candidate.chart_spec,
      rationale: `采用推荐候选 ${candidateId}`,
    });
    dispatch(
      applyChartPatch({
        taskId,
        datasetId,
        patch,
      }),
    );
    dispatch(selectCandidate(candidateId));
  };

  const nextCandidate = () => {
    if (candidates.length === 0) {
      return;
    }
    const nextIndex = (carouselIndex + 1) % candidates.length;
    setCarouselIndex(nextIndex);
    dispatch(selectCandidate(candidates[nextIndex].candidate_id));
  };

  const prevCandidate = () => {
    if (candidates.length === 0) {
      return;
    }
    const nextIndex = (carouselIndex - 1 + candidates.length) % candidates.length;
    setCarouselIndex(nextIndex);
    dispatch(selectCandidate(candidates[nextIndex].candidate_id));
  };

  return (
    <section className="card">
      <header className="card-header">
        <h2>推荐与惊喜</h2>
        <div className="inline-buttons">
          <button type="button" className="secondary-button" onClick={() => setViewMode(viewMode === "carousel" ? "gallery" : "carousel")}>
            切换为 {viewMode === "carousel" ? "Gallery" : "Carousel"}
          </button>
          <button type="button" className="secondary-button" onClick={handleRefresh} disabled={status === "loading" || !plan || !outputTable}>
            {status === "loading" ? "刷新中…" : "刷新推荐"}
          </button>
          <button type="button" className="primary-button" onClick={handleSurprise} disabled={!recommendations || recommendations.surprise_pool.length === 0}>
            给我惊喜
          </button>
        </div>
      </header>
      {error && <p className="error-text">{error}</p>}
      {viewMode === "carousel" ? (
        <div className="carousel">
          {currentCandidate ? (
            <div className="candidate-card">
              <div className="candidate-header">
                <strong>{currentCandidate.intent_tags.join(", ")}</strong>
                <span className="confidence">{Math.round(currentCandidate.confidence * 100)}%</span>
              </div>
              <p className="candidate-rationale">{currentCandidate.rationale}</p>
              <p className="candidate-coverage">{currentCandidate.coverage}</p>
              <div className="carousel-actions">
                <button type="button" className="secondary-button" onClick={prevCandidate}>
                  上一个
                </button>
                <button type="button" className="secondary-button" onClick={nextCandidate}>
                  下一个
                </button>
                <button type="button" className="primary-button" onClick={() => adoptCandidate(currentCandidate.candidate_id)}>
                  采纳候选
                </button>
              </div>
            </div>
          ) : (
            <p className="placeholder">暂无推荐候选。</p>
          )}
        </div>
      ) : (
        <ul className="gallery">
          {candidates.map((candidate) => (
            <li key={candidate.candidate_id} className={candidate.candidate_id === selectedCandidateId ? "gallery-item active" : "gallery-item"}>
              <header>
                <strong>{candidate.intent_tags.join(", ")}</strong>
                <span>{Math.round(candidate.confidence * 100)}%</span>
              </header>
              <p>{candidate.rationale}</p>
              {candidate.coverage && <p className="candidate-coverage">{candidate.coverage}</p>}
              <div className="gallery-actions">
                <button type="button" className="secondary-button" onClick={() => dispatch(selectCandidate(candidate.candidate_id))}>
                  查看
                </button>
                <button type="button" className="primary-button" onClick={() => adoptCandidate(candidate.candidate_id)}>
                  采纳候选
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
