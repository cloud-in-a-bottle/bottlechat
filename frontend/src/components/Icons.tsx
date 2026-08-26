import type { JSX } from "solid-js";

type IconProps = { size?: number } & JSX.SvgSVGAttributes<SVGSVGElement>;

function Icon(props: IconProps & { children: JSX.Element }) {
  const size = () => props.size ?? 16;
  return (
    <svg
      width={size()}
      height={size()}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.7"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      {...props}
    >
      {props.children}
    </svg>
  );
}

export const IconMenu = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 6h18M3 12h18M3 18h18" />
  </Icon>
);

export const IconPlus = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);

export const IconSearch = (p: IconProps) => (
  <Icon {...p} size={p.size ?? 14}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.2-3.2" />
  </Icon>
);

export const IconSend = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 19V5M5 12l7-7 7 7" />
  </Icon>
);

export const IconStop = (p: IconProps) => (
  <Icon {...p}>
    <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none" />
  </Icon>
);

export const IconShare = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7" />
    <path d="M12 15V3M8 7l4-4 4 4" />
  </Icon>
);

export const IconTrash = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 7h16M10 11v6M14 11v6" />
    <path d="M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12M9 7V4h6v3" />
  </Icon>
);

export const IconPencil = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17z" />
  </Icon>
);

export const IconDots = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="5" cy="12" r="1.4" fill="currentColor" stroke="none" />
    <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
    <circle cx="19" cy="12" r="1.4" fill="currentColor" stroke="none" />
  </Icon>
);

export const IconChevronRight = (p: IconProps) => (
  <Icon {...p} size={p.size ?? 13}>
    <path d="m9 5 7 7-7 7" />
  </Icon>
);

export const IconChevronDown = (p: IconProps) => (
  <Icon {...p} size={p.size ?? 12}>
    <path d="m5 9 7 7 7-7" />
  </Icon>
);

export const IconCopy = (p: IconProps) => (
  <Icon {...p} size={p.size ?? 14}>
    <rect x="9" y="9" width="11" height="11" rx="2" />
    <path d="M5 15V5a1 1 0 0 1 1-1h9" />
  </Icon>
);

export const IconRefresh = (p: IconProps) => (
  <Icon {...p} size={p.size ?? 14}>
    <path d="M20 12a8 8 0 1 1-2.6-5.9" />
    <path d="M20 4v5h-5" />
  </Icon>
);

export const IconSpark = (p: IconProps) => (
  <Icon {...p} size={p.size ?? 20}>
    <path d="M12 3l1.9 5.2L19 10l-5.1 1.8L12 17l-1.9-5.2L5 10l5.1-1.8z" />
  </Icon>
);

export const IconPlug = (p: IconProps) => (
  <Icon {...p} size={p.size ?? 20}>
    <path d="M9 3v6M15 3v6" />
    <path d="M6 9h12v3a6 6 0 0 1-12 0z" />
    <path d="M12 18v3" />
  </Icon>
);

export const IconLock = (p: IconProps) => (
  <Icon {...p} size={p.size ?? 20}>
    <rect x="4" y="10" width="16" height="10" rx="2" />
    <path d="M8 10V7a4 4 0 0 1 8 0v3" />
  </Icon>
);

export const IconWarning = (p: IconProps) => (
  <Icon {...p} size={p.size ?? 20}>
    <path d="M12 4.5 2.8 20h18.4z" />
    <path d="M12 10v4M12 17.2v.1" />
  </Icon>
);

export const IconBrain = (p: IconProps) => (
  <Icon {...p} size={p.size ?? 14}>
    <path d="M9.5 4a2.5 2.5 0 0 0-2.4 3.2A2.5 2.5 0 0 0 5.5 12a2.5 2.5 0 0 0 2 4 2.5 2.5 0 0 0 4.5-1.5V6.5A2.5 2.5 0 0 0 9.5 4Z" />
    <path d="M14.5 4a2.5 2.5 0 0 1 2.4 3.2A2.5 2.5 0 0 1 18.5 12a2.5 2.5 0 0 1-2 4 2.5 2.5 0 0 1-4.5-1.5" />
  </Icon>
);
