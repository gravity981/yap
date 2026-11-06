import logoNoTagline from "@/assets/brand/yap-logo-no-tagline.png";
import logoWithRobot from "@/assets/brand/yap-logo-with-robot.png";
import { cn } from "@/lib/utils";

// The product name and tagline are not translated
export const APP_NAME = "YAP";
const TAGLINE = "YAP Ain't a Portfolio – Think in theses. Invest by policy.";

/** Login picture: the robot with logo and tagline. */
export function RobotLogo({ className }: { className?: string }) {
  return (
    <img
      src={logoWithRobot}
      alt={TAGLINE}
      width={1460}
      height={695}
      className={cn("h-auto w-full rounded-xl", className)}
    />
  );
}

/** The logo without tagline, at the top of the sidebar and in the phone header. */
export function Logo({ className }: { className?: string }) {
  return (
    <img
      src={logoNoTagline}
      alt={APP_NAME}
      width={318}
      height={96}
      className={cn("h-auto rounded-md", className)}
    />
  );
}
