import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AutoWork AI — AI가 반복 업무를 대신합니다",
  description:
    "추가 채용 없이 주 10시간 절약. 미팅 요약·보고서·이메일 초안을 AI가 자동으로 처리합니다. 3일 내 도입 가능. 3주 무료 파일럿 신청 가능.",
  keywords: [
    "AI 업무 자동화",
    "미팅 요약 AI",
    "보고서 자동화",
    "이메일 자동화",
    "한국 스타트업 SaaS",
    "AI 도입",
  ],
  openGraph: {
    title: "AutoWork AI — AI가 반복 업무를 대신합니다",
    description:
      "추가 채용 없이 주 10시간 절약. 3일 내 도입, 3주 무료 파일럿.",
    type: "website",
    locale: "ko_KR",
    siteName: "AutoWork AI",
  },
  twitter: {
    card: "summary_large_image",
    title: "AutoWork AI — AI가 반복 업무를 대신합니다",
    description: "추가 채용 없이 주 10시간 절약. 3일 내 도입, 3주 무료 파일럿.",
  },
};

// 보드에서 제공할 실제 링크로 교체하세요
const CALENDLY_URL = "https://calendly.com/autowork-ai/demo";
const TALLY_URL = "https://tally.so/r/autowork-pilot";

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="fixed top-0 w-full bg-white/90 backdrop-blur-md border-b border-gray-100 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-sm">A</span>
              </div>
              <span className="font-bold text-gray-900 text-lg">AutoWork AI</span>
            </div>
            <div className="hidden md:flex items-center gap-8">
              <Link href="#features" className="text-gray-600 hover:text-gray-900 text-sm">
                기능
              </Link>
              <Link href="#how-it-works" className="text-gray-600 hover:text-gray-900 text-sm">
                도입 방법
              </Link>
              <Link href="#pricing" className="text-gray-600 hover:text-gray-900 text-sm">
                가격
              </Link>
              <a
                href={CALENDLY_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
              >
                데모 예약
              </a>
            </div>
            {/* Mobile CTA */}
            <a
              href={CALENDLY_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="md:hidden bg-blue-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium"
            >
              데모 예약
            </a>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-24 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-700 px-4 py-2 rounded-full text-sm font-medium mb-8">
            <span>✨</span>
            <span>3주 무료 파일럿 · 지금 신청 가능</span>
          </div>
          <h1 className="text-5xl md:text-6xl font-bold text-gray-900 leading-tight mb-6">
            AI가 반복 업무를 대신합니다
            <br />
            <span className="text-blue-600">직원은 창의적 일에 집중하세요</span>
          </h1>
          <p className="text-xl text-gray-600 mb-4 max-w-2xl mx-auto">
            추가 채용 없이 <strong>주 10시간 절약</strong>. 3일 내 도입 가능.
          </p>
          <p className="text-gray-500 mb-10 max-w-xl mx-auto">
            미팅 요약 · 보고서 작성 · 이메일 초안을 AI가 자동으로 처리합니다.
            한국 스타트업과 중소기업을 위한 AI 업무 자동화 솔루션.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href={CALENDLY_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-blue-600 text-white px-8 py-4 rounded-xl text-lg font-medium hover:bg-blue-700 transition-colors shadow-lg shadow-blue-100"
            >
              30분 데모 예약하기
            </a>
            <a
              href={TALLY_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="border-2 border-blue-600 text-blue-600 px-8 py-4 rounded-xl text-lg font-medium hover:bg-blue-50 transition-colors"
            >
              3주 무료 파일럿 신청
            </a>
          </div>
          <p className="mt-4 text-sm text-gray-400">신용카드 불필요 · 계약 없음 · 언제든 취소 가능</p>
        </div>
      </section>

      {/* Social Proof */}
      <section className="py-8 bg-gray-50 border-y border-gray-100 px-4">
        <div className="max-w-4xl mx-auto flex flex-wrap justify-center gap-8 text-center">
          {[
            { stat: "80%", label: "미팅 후속 처리 절감" },
            { stat: "70%", label: "보고서 작성 시간 절감" },
            { stat: "3일", label: "평균 도입 기간" },
            { stat: "100만원", label: "월 비용 (파트타임 대비 70% 절감)" },
          ].map((item) => (
            <div key={item.label} className="px-4">
              <div className="text-3xl font-bold text-blue-600">{item.stat}</div>
              <div className="text-sm text-gray-500 mt-1">{item.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Value Props */}
      <section id="features" className="py-20 px-4">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">왜 AutoWork AI인가요?</h2>
            <p className="text-gray-600 text-lg">업무 시간을 아끼고, 비용을 줄이고, 팀이 중요한 일에 집중하게 합니다</p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              {
                icon: "⏱",
                title: "시간 절약",
                description:
                  "보고서·이메일 초안·데이터 요약 작성 시간을 80% 단축합니다. 주 10시간 이상 확보.",
                highlight: "업무 시간 80% 단축",
              },
              {
                icon: "💰",
                title: "비용 절감",
                description:
                  "월 100만원으로 파트타임 채용 대비 70% 절감. 추가 인원 없이 업무 처리량을 늘립니다.",
                highlight: "채용 대비 70% 절감",
              },
              {
                icon: "⚡",
                title: "즉시 적용",
                description:
                  "Slack·카카오톡·Notion 연동. 복잡한 설정 없이 3일 내 팀 전체가 사용할 수 있습니다.",
                highlight: "3일 내 도입",
              },
              {
                icon: "🇰🇷",
                title: "한국어 특화",
                description:
                  "국내 기업 문서 포맷, 보고서 양식, 한국식 이메일 어조를 완벽하게 지원합니다.",
                highlight: "한국 기업 최적화",
              },
            ].map((prop) => (
              <div
                key={prop.title}
                className="bg-white rounded-2xl p-8 shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
              >
                <div className="text-4xl mb-4">{prop.icon}</div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{prop.title}</h3>
                <p className="text-gray-600 mb-4 text-sm leading-relaxed">{prop.description}</p>
                <div className="text-blue-600 font-semibold text-sm">{prop.highlight}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-20 bg-gray-50 px-4">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">3단계로 시작하세요</h2>
            <p className="text-gray-600 text-lg">복잡한 설치나 교육 없이, 오늘 바로 시작합니다</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8 relative">
            {/* Connector line for desktop */}
            <div className="hidden md:block absolute top-12 left-1/3 right-1/3 h-0.5 bg-blue-200 z-0" />
            {[
              {
                step: "01",
                title: "연동",
                description:
                  "Slack, 카카오톡, Notion, 구글 워크스페이스에 AutoWork AI를 연결합니다. 5분이면 충분합니다.",
                icon: "🔌",
              },
              {
                step: "02",
                title: "자동화",
                description:
                  "미팅이 끝나면 자동 요약, 보고서는 팀원 업무를 취합해 자동 완성, 이메일은 초안이 자동으로 작성됩니다.",
                icon: "🤖",
              },
              {
                step: "03",
                title: "결과 확인",
                description:
                  "절약된 시간과 처리한 업무를 대시보드에서 확인합니다. ROI를 매일 측정할 수 있습니다.",
                icon: "📊",
              },
            ].map((step) => (
              <div key={step.step} className="relative z-10 text-center">
                <div className="w-24 h-24 bg-white rounded-2xl border-2 border-blue-100 flex items-center justify-center text-4xl mx-auto mb-6 shadow-sm">
                  {step.icon}
                </div>
                <div className="text-blue-600 font-bold text-sm mb-2">STEP {step.step}</div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{step.title}</h3>
                <p className="text-gray-600 text-sm leading-relaxed">{step.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Detail */}
      <section className="py-20 px-4">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">3가지 핵심 기능</h2>
            <p className="text-gray-600 text-lg">반복 업무의 대부분을 커버합니다</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: "🎙️",
                title: "AI 미팅 요약",
                description:
                  "Zoom, Teams 녹취 파일을 업로드하면 AI가 자동으로 요약하고 담당자별 액션 아이템을 추출합니다.",
                stat: "미팅 후속 처리 80% 절감",
              },
              {
                icon: "📋",
                title: "AI 보고서 자동 생성",
                description:
                  "팀원 업무를 취합하여 주간/일일 보고서를 자동 완성합니다. 임원 보고용 요약본도 자동 생성.",
                stat: "보고서 작성 시간 70% 절감",
              },
              {
                icon: "✉️",
                title: "AI 이메일/제안서",
                description:
                  "회사 컨텍스트를 학습한 AI가 맞춤형 영업 이메일과 제안서 초안을 즉시 작성합니다.",
                stat: "영업 이메일 작성 60% 절감",
              },
            ].map((feature) => (
              <div
                key={feature.title}
                className="bg-gradient-to-br from-blue-50 to-white rounded-2xl p-8 border border-blue-100"
              >
                <div className="text-4xl mb-4">{feature.icon}</div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{feature.title}</h3>
                <p className="text-gray-600 mb-4 text-sm leading-relaxed">{feature.description}</p>
                <div className="text-blue-600 font-semibold text-sm bg-blue-50 inline-block px-3 py-1 rounded-full">
                  {feature.stat}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-20 bg-gray-50 px-4">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-6">
            <div className="inline-flex items-center gap-2 bg-green-50 text-green-700 px-4 py-2 rounded-full text-sm font-medium mb-4">
              <span>🎁</span>
              <span>지금 신청하면 3주 무료 파일럿 제공</span>
            </div>
            <h2 className="text-3xl font-bold text-gray-900 mb-4">투명한 구독 요금</h2>
            <p className="text-gray-600 text-lg">팀 규모에 맞는 플랜을 선택하세요. 파일럿 후 부담 없이 결정하세요.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8 mt-12">
            {[
              {
                name: "스타터",
                price: "50만원",
                description: "소규모 팀",
                members: "5명 이하",
                features: [
                  "월 미팅 요약 50건",
                  "보고서 자동 생성",
                  "이메일 초안 무제한",
                  "슬랙 연동",
                ],
                highlight: false,
                cta: "파일럿 신청",
                ctaHref: TALLY_URL,
              },
              {
                name: "프로",
                price: "80만원",
                description: "성장하는 팀",
                members: "20명 이하",
                features: [
                  "미팅 요약 무제한",
                  "보고서 자동 생성",
                  "이메일/제안서 무제한",
                  "CRM 연동",
                  "우선 지원",
                ],
                highlight: true,
                cta: "파일럿 신청",
                ctaHref: TALLY_URL,
              },
              {
                name: "엔터프라이즈",
                price: "협의",
                description: "대규모 조직",
                members: "무제한",
                features: [
                  "모든 기능 무제한",
                  "커스텀 AI 학습",
                  "전담 CS 매니저",
                  "API 연동",
                  "보안 감사",
                ],
                highlight: false,
                cta: "데모 예약",
                ctaHref: CALENDLY_URL,
              },
            ].map((plan) => (
              <div
                key={plan.name}
                className={`rounded-2xl p-8 border ${
                  plan.highlight
                    ? "border-blue-600 bg-blue-600 text-white shadow-xl shadow-blue-100"
                    : "border-gray-200 bg-white"
                }`}
              >
                {plan.highlight && (
                  <div className="bg-white/20 text-white text-xs font-bold px-3 py-1 rounded-full inline-block mb-4">
                    가장 인기 있는 플랜
                  </div>
                )}
                <div className={`text-sm font-medium mb-2 ${plan.highlight ? "text-blue-100" : "text-gray-500"}`}>
                  {plan.description}
                </div>
                <div className="text-2xl font-bold mb-1">{plan.name}</div>
                <div className={`text-3xl font-bold mb-1 ${plan.highlight ? "text-white" : "text-gray-900"}`}>
                  {plan.price}
                  {plan.price !== "협의" && <span className="text-lg font-normal">/월</span>}
                </div>
                <div className={`text-sm mb-6 ${plan.highlight ? "text-blue-100" : "text-gray-500"}`}>
                  {plan.members}
                </div>
                <ul className="space-y-3 mb-8">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm">
                      <span className={plan.highlight ? "text-blue-200" : "text-blue-600"}>✓</span>
                      {f}
                    </li>
                  ))}
                </ul>
                <a
                  href={plan.ctaHref}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`block text-center py-3 rounded-xl font-medium transition-colors ${
                    plan.highlight
                      ? "bg-white text-blue-600 hover:bg-blue-50"
                      : "bg-blue-600 text-white hover:bg-blue-700"
                  }`}
                >
                  {plan.cta}
                </a>
              </div>
            ))}
          </div>
          <p className="text-center text-sm text-gray-500 mt-8">
            모든 플랜 · 3주 무료 파일럿 포함 · 계약 없이 취소 가능
          </p>
        </div>
      </section>

      {/* CTA Section */}
      <section id="demo" className="py-24 px-4 bg-blue-600">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-4xl font-bold text-white mb-4">
            오늘 바로 시작하세요
          </h2>
          <p className="text-blue-100 text-xl mb-10">
            30분 데모로 AutoWork AI가 우리 팀에 맞는지 확인하거나,
            <br className="hidden sm:block" />
            3주 무료 파일럿으로 직접 경험해보세요.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href={CALENDLY_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-white text-blue-600 px-8 py-4 rounded-xl text-lg font-semibold hover:bg-blue-50 transition-colors shadow-lg"
            >
              📅 30분 데모 예약하기
            </a>
            <a
              href={TALLY_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="border-2 border-white text-white px-8 py-4 rounded-xl text-lg font-semibold hover:bg-blue-700 transition-colors"
            >
              🚀 3주 무료 파일럿 신청
            </a>
          </div>
          <p className="mt-6 text-blue-200 text-sm">
            신용카드 불필요 · 파일럿 후 구독 여부 자유롭게 결정
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-gray-400 py-12 px-4">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-start gap-8 mb-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                  <span className="text-white font-bold text-sm">A</span>
                </div>
                <span className="font-bold text-white text-lg">AutoWork AI</span>
              </div>
              <p className="text-sm text-gray-500 max-w-xs">
                한국 스타트업과 중소기업을 위한 AI 업무 자동화 솔루션
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <h4 className="text-white font-medium text-sm">문의</h4>
              <a
                href="mailto:hello@autowork.ai"
                className="text-sm text-gray-400 hover:text-white transition-colors"
              >
                hello@autowork.ai
              </a>
              <a
                href={CALENDLY_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
              >
                데모 예약 →
              </a>
            </div>
          </div>
          <div className="border-t border-gray-800 pt-8 flex flex-col sm:flex-row justify-between items-center gap-4 text-sm">
            <p>© 2026 AutoWork AI. All rights reserved.</p>
            <div className="flex gap-6">
              <Link href="/privacy" className="hover:text-white transition-colors">
                개인정보처리방침
              </Link>
              <Link href="/terms" className="hover:text-white transition-colors">
                이용약관
              </Link>
            </div>
          </div>
        </div>
      </footer>
    </main>
  );
}
