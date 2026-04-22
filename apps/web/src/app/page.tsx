import Link from "next/link";

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="fixed top-0 w-full bg-white/80 backdrop-blur-md border-b border-gray-100 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-sm">A</span>
              </div>
              <span className="font-bold text-gray-900 text-lg">AutoWork AI</span>
            </div>
            <div className="hidden md:flex items-center gap-8">
              <Link href="#features" className="text-gray-600 hover:text-gray-900 text-sm">기능</Link>
              <Link href="#pricing" className="text-gray-600 hover:text-gray-900 text-sm">가격</Link>
              <Link href="/login" className="text-gray-600 hover:text-gray-900 text-sm">로그인</Link>
              <Link
                href="/signup"
                className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
              >
                무료 체험
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-20 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-700 px-4 py-2 rounded-full text-sm font-medium mb-6">
            <span>🚀</span>
            <span>AI 업무 자동화로 생산성 3배 향상</span>
          </div>
          <h1 className="text-5xl md:text-6xl font-bold text-gray-900 leading-tight mb-6">
            반복 업무는 AI에게,
            <br />
            <span className="text-blue-600">핵심 업무에 집중하세요</span>
          </h1>
          <p className="text-xl text-gray-600 mb-10 max-w-2xl mx-auto">
            미팅 요약, 보고서 작성, 이메일 초안을 AI가 자동으로 처리합니다.
            한국 스타트업과 중소기업을 위한 AI 업무 자동화 솔루션.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/signup"
              className="bg-blue-600 text-white px-8 py-4 rounded-xl text-lg font-medium hover:bg-blue-700 transition-colors"
            >
              14일 무료 체험 시작
            </Link>
            <Link
              href="#demo"
              className="border border-gray-300 text-gray-700 px-8 py-4 rounded-xl text-lg font-medium hover:bg-gray-50 transition-colors"
            >
              데모 보기
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20 bg-gray-50 px-4">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">3가지 핵심 기능</h2>
            <p className="text-gray-600 text-lg">업무 시간의 60~80%를 절약하는 AI 자동화</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: "🎙️",
                title: "AI 미팅 요약",
                description: "Zoom, Teams 녹취 파일을 업로드하면 AI가 자동으로 요약하고 담당자별 액션 아이템을 추출합니다.",
                stat: "미팅 후속 처리 80% 절감",
              },
              {
                icon: "📊",
                title: "AI 보고서 자동 생성",
                description: "팀원 업무를 취합하여 주간/일일 보고서를 자동 완성합니다. 임원 보고용 요약본도 자동 생성.",
                stat: "보고서 작성 시간 70% 절감",
              },
              {
                icon: "✉️",
                title: "AI 이메일/제안서",
                description: "회사 컨텍스트를 학습한 AI가 맞춤형 영업 이메일과 제안서 초안을 즉시 작성합니다.",
                stat: "영업 이메일 작성 60% 절감",
              },
            ].map((feature) => (
              <div key={feature.title} className="bg-white rounded-2xl p-8 shadow-sm border border-gray-100">
                <div className="text-4xl mb-4">{feature.icon}</div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{feature.title}</h3>
                <p className="text-gray-600 mb-4">{feature.description}</p>
                <div className="text-blue-600 font-medium text-sm">{feature.stat}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">투명한 구독 요금</h2>
            <p className="text-gray-600 text-lg">팀 규모에 맞는 플랜을 선택하세요</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                name: "스타터",
                price: "50만원",
                description: "소규모 팀",
                members: "5명 이하",
                features: ["월 미팅 요약 50건", "보고서 자동 생성", "이메일 초안 무제한", "슬랙 연동"],
                highlight: false,
              },
              {
                name: "프로",
                price: "80만원",
                description: "성장하는 팀",
                members: "20명 이하",
                features: ["미팅 요약 무제한", "보고서 자동 생성", "이메일/제안서 무제한", "CRM 연동", "우선 지원"],
                highlight: true,
              },
              {
                name: "엔터프라이즈",
                price: "협의",
                description: "대규모 조직",
                members: "무제한",
                features: ["모든 기능 무제한", "커스텀 AI 학습", "전담 CS 매니저", "API 연동", "보안 감사"],
                highlight: false,
              },
            ].map((plan) => (
              <div
                key={plan.name}
                className={`rounded-2xl p-8 border ${
                  plan.highlight
                    ? "border-blue-600 bg-blue-600 text-white shadow-lg shadow-blue-100"
                    : "border-gray-200 bg-white"
                }`}
              >
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
                      <span>{plan.highlight ? "✓" : "✓"}</span>
                      {f}
                    </li>
                  ))}
                </ul>
                <Link
                  href="/signup"
                  className={`block text-center py-3 rounded-xl font-medium transition-colors ${
                    plan.highlight
                      ? "bg-white text-blue-600 hover:bg-blue-50"
                      : "bg-blue-600 text-white hover:bg-blue-700"
                  }`}
                >
                  {plan.price === "협의" ? "문의하기" : "시작하기"}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-gray-400 py-12 px-4">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center gap-2 mb-8">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">A</span>
            </div>
            <span className="font-bold text-white text-lg">AutoWork AI</span>
          </div>
          <div className="border-t border-gray-800 pt-8 text-sm">
            <p>© 2026 AutoWork AI. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </main>
  );
}
