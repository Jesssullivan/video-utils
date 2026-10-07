import type { PageServerLoad } from './$types';
import { getJob, listJobs, runControl } from '$lib/server/control-client';

const PROJECTED_JOBS = 8;

// Share MP4s of admitted sources come from succeeded share_export jobs (existing /api/artifacts/[id]).
export const load: PageServerLoad = async ({ parent, request }) => {
	const { graph } = await parent();
	const shares: { source_artifact_id: string; job_id: string; artifact_id: string; sha256: string; size_bytes: number }[] = [];
	let shareError = null;
	for (const source of graph?.admitted_sources ?? []) {
		const jobs = await runControl(listJobs(source.source_artifact_id), request.signal);
		if (!jobs.ok) {
			shareError = jobs.error;
			continue;
		}
		const succeeded = jobs.data.jobs.filter((job) => job.state === 'succeeded').slice(0, PROJECTED_JOBS);
		for (const job of succeeded) {
			const projection = await runControl(getJob(job.job_id), request.signal);
			if (!projection.ok) continue;
			for (const artifact of projection.data.artifacts) {
				if (artifact.role === 'share_mp4' && artifact.downloadable) {
					shares.push({ source_artifact_id: source.source_artifact_id, job_id: job.job_id, artifact_id: artifact.artifact_id, sha256: artifact.sha256, size_bytes: artifact.size_bytes });
				}
			}
		}
	}
	return { shares, shareError };
};
