import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { MessageCard } from './MessageCard';

const favoritesMock = vi.fn();
const addFavoriteMock = vi.fn();
const removeFavoriteMock = vi.fn();

vi.mock('@/api/hooks', () => ({
  useFavorites: favoritesMock,
  useAddFavorite: addFavoriteMock,
  useRemoveFavorite: removeFavoriteMock,
}));

const message = {
  id: 'msg-1',
  channel_kind: 'tg',
  channel_site: 'test-channel',
  published_at: '2026-05-15T12:30:00Z',
  text: 'Тестовое сообщение для карточки.',
  author: { name: 'Автор' },
  lang: 'ru',
  url: 'https://example.com/message/1',
  annotation: {
    sentiment: { label: 'positive' },
    topics: [{ slug: 'invest' }, { slug: 'market' }],
    is_ad: true,
  },
} as const;

describe('MessageCard', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    favoritesMock.mockReturnValue({ data: [] });
    addFavoriteMock.mockReturnValue({ mutate: vi.fn() });
    removeFavoriteMock.mockReturnValue({ mutate: vi.fn() });
  });

  it('renders message details and toggles favorite', async () => {
    const add = vi.fn();
    addFavoriteMock.mockReturnValue({ mutate: add });

    render(
      <MemoryRouter>
        <MessageCard message={message} isNew />
      </MemoryRouter>
    );

    expect(screen.getByText('Telegram')).toBeInTheDocument();
    expect(screen.getByText('Автор')).toBeInTheDocument();
    expect(screen.getByText('Позитив')).toBeInTheDocument();
    expect(screen.getByText('#invest')).toBeInTheDocument();
    expect(screen.getByText('#market')).toBeInTheDocument();
    expect(screen.getByText(/Тестовое сообщение/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Источник/ })).toHaveAttribute('href', message.url);

    const button = screen.getByRole('button', { name: /В избранное/ });
    await userEvent.click(button);

    expect(add).toHaveBeenCalledWith({ target_kind: 'message', target_ref: message.id });
  });

  it('shows favorite state and removes favorite', async () => {
    const remove = vi.fn();
    favoritesMock.mockReturnValue({ data: [{ target_ref: message.id, target_kind: 'message' }] });
    removeFavoriteMock.mockReturnValue({ mutate: remove });

    render(
      <MemoryRouter>
        <MessageCard message={message} />
      </MemoryRouter>
    );

    const button = screen.getByRole('button', { name: /Убрать из избранного/ });
    await userEvent.click(button);

    expect(remove).toHaveBeenCalledWith({ target_kind: 'message', target_ref: message.id });
  });
});
