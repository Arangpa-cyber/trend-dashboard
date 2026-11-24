-- 추세 대시보드 일봉 메모(2026-11-24) — 트레이딩:무살과 같은 Supabase 프로젝트에 표 하나를 더한다.
-- Supabase 대시보드 SQL Editor에 통째로 붙여넣고 Run. 여러 번 실행해도 안전하다(이미 있으면 건너뜀).
-- 종목·날짜(미국 거래일)마다 한 줄. RLS로 본인 메모만 읽고 쓴다. 무살 회원 탈퇴(auth.users 삭제) 때 함께 지워진다.
-- 무살 표(buys·sells 등)와 무살의 데이터 초기화 함수는 건드리지 않는다.

create table if not exists public.td_memos (
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  sym text not null check (char_length(sym) between 1 and 12),
  day date not null,
  text text not null check (char_length(text) between 1 and 1000),
  updated_at timestamptz not null default now(),
  primary key (user_id, sym, day)
);

alter table public.td_memos enable row level security;
drop policy if exists "own rows" on public.td_memos;
create policy "own rows" on public.td_memos for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on public.td_memos to authenticated;
