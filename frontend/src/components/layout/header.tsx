"use client"

import Image from "next/image"

export function Header() {
  return (
    <header className="border-b border-[#2A3340] bg-[#0B0F14] py-4">
      <div className="container mx-auto max-w-6xl px-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Image
              src="/images/logo.jpg"
              alt="EnergyMind"
              width={48}
              height={48}
              className="rounded-xl object-cover"
            />
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">EnergyMind</h1>
              <p className="text-sm text-[#94A3B8]">Legal RAG · Renewable Energy</p>
            </div>
          </div>
        </div>
      </div>
    </header>
  )
}
