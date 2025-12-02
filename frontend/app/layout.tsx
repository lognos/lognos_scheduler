import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lognos",
  description: "AI Assistant for Lognos",
  icons: {
    icon: '/circle_favicon.png',
  },
};

import { AuthProvider } from "../components/providers/AuthProvider";
import { UserProvider } from "@/lib/contexts/UserContext";
import { ProjectProvider } from "@/lib/contexts/ProjectContext";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <AuthProvider>
          <UserProvider>
            <ProjectProvider>
              {children}
            </ProjectProvider>
          </UserProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
