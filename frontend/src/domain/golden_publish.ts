/** 金记录发布申请领域层：受理单明细、领取/续领确认与合并侧认可状态。 */
import { request } from '@/api/client'

export type PublishDetailLine = {
  金记录标识: string
  合并任务ID: number | null
  合并任务: string
  确认类型: string
  更正确认号: string
  替代金记录: string
}

export type MergeSideState = {
  候选组: string
  认可金记录: string
  认可合并任务ID: number | null
  认可合并任务: string
  更正确认号: string
  替代关系: { 被替代金记录: string; 替代为金记录: string; 更正确认号: string }[]
  已合并产物: string[]
}

export type PublishApplicationDetail = {
  id: number
  申请编号: string
  发布批次: string
  status: string
  领取状态: string
  实体编码: string
  候选组: string
  合并任务ID: number | null
  引用金记录: string[]
  发布明细: PublishDetailLine[]
  采用金记录: string
  更正确认号: string
  金记录数: string
  发布时间: string
  版本标识: string
  核对说明: string
  版本冲突: boolean
  合并侧: MergeSideState
  可领取: boolean
  已发出: boolean
}

export async function fetchPublishApplication(id: number): Promise<PublishApplicationDetail> {
  const response = await request(`/api/golden_publish/${id}/application`)
  if (!response.ok) throw new Error('发布申请明细读取失败')
  return (await response.json()) as PublishApplicationDetail
}

export async function claimPublishApplication(
  id: number,
): Promise<{ ok: boolean; message: string }> {
  const response = await request(`/api/golden_publish/${id}/claim`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
  return (await response.json()) as { ok: boolean; message: string }
}
