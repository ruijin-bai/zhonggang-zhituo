"use client";
import {useState} from "react";
import {DEMO_FALLBACK_ALLOWED,demoRedTeam,demoStrategyDraft} from "@/lib/demo-operating";
const API=process.env.NEXT_PUBLIC_API_BASE_URL??"http://127.0.0.1:8000";
export default function StrategyLab({id}:{id:string}){
 const [draft,setDraft]=useState<any>(null),[red,setRed]=useState<any>(null),[busy,setBusy]=useState(""),[fallback,setFallback]=useState(false),[error,setError]=useState("");
 async function run(kind:"generate"|"red-team"){setBusy(kind);setFallback(false);setError("");try{const r=await fetch(`${API}/api/opportunities/${id}/strategy/${kind}`,{method:"POST"});if(!r.ok)throw new Error("service unavailable");const d=await r.json();if(kind==="generate")setDraft(d);else setRed(d)}catch{if(DEMO_FALLBACK_ALLOWED){setFallback(true);if(kind==="generate")setDraft(demoStrategyDraft);else setRed(demoRedTeam)}else{setError("AI/API 服务不可用，请检查运行环境后重试。")}}finally{setBusy("")}}
 return <section className="section"><div className="section-head"><div><h2>AI 策略实验室</h2><p className="muted small">先生成策略假设，再由独立红队主动寻找失败路径。</p></div><div className="lab-buttons"><button className="primary-button" disabled={!!busy} onClick={()=>run("generate")}>{busy==="generate"?"生成中…":"生成策略初稿"}</button><button className="secondary-button" disabled={!!busy} onClick={()=>run("red-team")}>{busy==="red-team"?"挑战中…":"启动红队挑战"}</button></div></div>
 {fallback&&<div className="policy-note">当前 AI/API 不可用，已切换至离线演示结果；经营主链可继续演示。</div>}
 {error&&<div className="error-box">{error}</div>}
 {draft&&<div className="lab-result"><div className="eyebrow">STRATEGY DRAFT · {draft.mode}</div><h3>{draft.draft.win_theme}</h3><p>{draft.draft.client_need}</p><b>差异化假设</b><ul>{draft.draft.differentiation.map((x:string)=><li key={x}>{x}</li>)}</ul><b>待验证假设 / 缺口</b><ul>{[...draft.draft.gaps,...draft.draft.assumptions].map((x:string)=><li key={x}>{x}</li>)}</ul></div>}
 {red&&<div className="lab-result red-team"><div className="eyebrow">RED TEAM · {red.mode}</div><h3>{red.challenge.verdict}</h3><b>为什么可能拿不到</b><ul>{red.challenge.failure_modes.map((x:string)=><li key={x}>{x}</li>)}</ul><b>缺失证据</b><ul>{red.challenge.missing_evidence.map((x:string)=><li key={x}>{x}</li>)}</ul><b>反制动作</b><ol>{red.challenge.counter_moves.map((x:string)=><li key={x}>{x}</li>)}</ol></div>}
 </section>
}
