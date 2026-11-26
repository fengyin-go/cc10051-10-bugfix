/** 金记录合并领域层：合并行的发布申请提交与按候选组归集的申请列表。 */
import { request } from '@/api/client'
import type { MergeSideState } from './golden_publish'

export type MergePublishApplication = {
  id: number
  申请编号: string
  发布批次: string
  status: string
  领取状态: string
  引用金记录: string[]
  采用金记录: string
  更正确认号: string
  版本冲突: boolean
}

export type MergePublishApplications = {
  候选组: string
  合并任务ID: number
  合并任务: string
  合并结果: string
  合并侧: MergeSideState
  applications: MergePublishApplication[]
}

export async function fetchMergePublishApplications(
  mergeId: number,
): Promise<MergePublishApplications> {
  const response = await request(`/api/golden_merge/${mergeId}/publish_applications`)
  if (!response.ok) throw new Error('合并行的发布申请读取失败')
  return (await response.json()) as MergePublishApplications
}

export async function submitPublishApplication(
  mergeId: number,
): Promise<{ ok: boolean; message: string }> {
  const response = await request(`/api/golden_merge/${mergeId}/publish_application`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
  return (await response.json()) as { ok: boolean; message: string }
}
