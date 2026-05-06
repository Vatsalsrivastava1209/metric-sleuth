import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "../components/ThemeProvider";
import { Toaster } from "sonner";
import { PaymentBanner } from "../components/PaymentBanner";

export const metadata: Metadata = {
  title: "Metric Sleuth | Client anomaly detection for ecommerce agencies",
  description:
    "Spot client KPI anomalies early, explain likely drivers, and ship white-label briefs before the client asks what happened.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full flex flex-col">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          <PaymentBanner />
          {children}
          <Toaster richColors position="top-right" />
        </ThemeProvider>
      </body>
    </html>
  );
}
