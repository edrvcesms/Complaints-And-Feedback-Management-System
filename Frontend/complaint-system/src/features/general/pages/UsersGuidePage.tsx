import maryapp from "../../../assets/maryapp.jpg";

const youtubeVideoUrl = "https://www.youtube.com/watch?v=rK3Cgc43hzo";

export const UsersGuidePage: React.FC = () => {
  return (
    <main className="min-h-screen bg-white text-slate-900">
      <div className="mx-auto max-w-4xl px-5 py-8 sm:px-8 sm:py-12">
        <header className="flex items-center gap-3 border-b border-slate-200 pb-6">
          <img src={maryapp} alt="Mary App logo" className="h-11 w-11 rounded-full object-cover" />
          <div>
            <p className="text-sm font-semibold text-[#17643b]">Mary App</p>
            <p className="text-xs text-slate-500">User guide</p>
          </div>
        </header>

        <section className="pt-10" aria-labelledby="guide-title">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#c25b35]">Getting started</p>
          <h1 id="guide-title" className="mt-3 text-3xl font-bold tracking-tight text-[#123d2b] sm:text-4xl">How to use Mary App</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">A short guide to submitting complaints and following their progress.</p>

          <div className="relative mt-8 aspect-video overflow-hidden rounded-lg border border-slate-200 bg-black">
            {youtubeVideoUrl && (
              <iframe
                src={youtubeVideoUrl}
                title="Mary App user guide video"
                className="absolute inset-0 h-full w-full border-0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
              />
            )}
          </div>
        </section>
      </div>
    </main>
  );
};