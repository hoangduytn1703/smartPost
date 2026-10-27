/** Download every rendered clip of a job, then open the iPhone posting step for that job. */
export function handoffToPhone(jobId: number, navigate: (to: string) => void) {
  const link = document.createElement("a");
  link.href = `/api/jobs/${jobId}/zip`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  navigate(`/phone?job=${jobId}`);
}
