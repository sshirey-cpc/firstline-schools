import Image from 'next/image';

export default function Header() {
  return (
    <header className="bg-gradient-to-r from-fls-navy via-fls-blue to-fls-navy shadow-2xl border-b-4 border-fls-orange">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-24">
          <div className="flex items-center gap-8">
            <div className="bg-white px-6 py-3 rounded-lg shadow-xl">
              <Image
                src="/fls-logo.png"
                alt="FirstLine Schools Logo"
                width={220}
                height={60}
                className="h-14 w-auto"
                priority
              />
            </div>
            <div className="h-16 w-px bg-gradient-to-b from-transparent via-white to-transparent opacity-40"></div>
            <div>
              <h1 className="text-3xl font-bold text-white tracking-tight">
                Grow Dashboard
              </h1>
              <p className="text-blue-200 text-sm font-medium mt-1">
                Teacher Action Steps & Goals
              </p>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
