// Copyright (C) 2011-2018 ycmd contributors
//
// This file is part of ycmd.
//
// ycmd is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// ycmd is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with ycmd.  If not, see <http://www.gnu.org/licenses/>.

#include "Candidate.h"
#include "Result.h"

namespace YouCompleteMe {

namespace {

size_t LongestCommonSubsequenceLength( const CharacterSequence &first,
                                       const CharacterSequence &second ) {
  const auto &longer  = first.size() > second.size() ? first  : second;
  const auto &shorter = first.size() > second.size() ? second : first;

  size_t longer_len  = longer.size();
  size_t shorter_len = shorter.size();

  // 迭代找出i,j时的最长通用子串, 并用表记录下来
  // j+1记录为current j字符比对后最长数, j为previous比对前最长数
  // 所以当i加入一个新字符并匹配时, 比对后最长数j+1 = *之前*比对前最长数 + 1 (i只有一个字符，最多加1, 所以不是当前比对前最长数)
  // 不匹配时，要么保留之前的最长值，要么保留当前前一个字符比对的最长值
  std::vector< size_t > previous( shorter_len + 1, 0 );
  std::vector< size_t > current(  shorter_len + 1, 0 );

  size_t full_matched_len = 0; // 已经前面都匹配上了，达到最大值，可直接从后面进行比较。
  for ( size_t i = 0; i < longer_len; ++i ) {
    for ( size_t j = full_matched_len; j < shorter_len; ++j ) {
      if ( longer[ i ]->EqualsBase( *shorter[ j ] ) ) {
        current[ j + 1 ] = previous[ j ] + 1;
      } else {
        current[ j + 1 ] = std::max( current[ j ], previous[ j + 1 ] );
      }
    }

    for ( size_t j = full_matched_len; j < shorter_len; ++j ) {
      previous[ j + 1 ] = current[ j + 1 ];
    }
    for ( size_t j = full_matched_len; j < shorter_len; ++j ) {
      if (j + 1 == previous[ j + 1 ]) full_matched_len = j + 1;
      else { break; }
    }
  }

  return current[ shorter_len ];
}


} // unnamed namespace

/*
void Candidate::ComputeCaseSwappedText() {
  for ( const auto &character : Characters() ) {
    case_swapped_text_.append( character->SwappedCase() );
  }
}
*/


void Candidate::ComputeWordBoundaryChars() {
  const CharacterSequence &characters = Characters();

  auto character_pos = characters.begin();
  if ( character_pos == characters.end() ) {
    return;
  }

  const auto &first_character = *character_pos;
  if ( !first_character->IsPunctuation() ) {
    word_boundary_chars_.push_back( first_character );
  }

  auto previous_character_pos = characters.begin();
  ++character_pos;
  for ( ; character_pos != characters.end(); ++previous_character_pos,
                                             ++character_pos ) {
    const auto &previous_character = *previous_character_pos;
    const auto &character = *character_pos;

    if ( ( !previous_character->IsUppercase() && character->IsUppercase() ) ||
         ( previous_character->IsPunctuation() && character->IsLetter() ) ) {
      word_boundary_chars_.push_back( character );
    }
  }
}


/*
void Candidate::ComputeTextIsLowercase() {
  for ( const auto &character : Characters() ) {
    if ( character->IsUppercase() ) {
      text_is_lowercase_ = false;
      return;
    }
  }

  text_is_lowercase_ = true;
}
*/


Candidate::Candidate( const std::string &text )
  : Word( text ) {
  // ComputeCaseSwappedText();
  ComputeWordBoundaryChars();
  // ComputeTextIsLowercase();
}

/*
Result Candidate::QueryMatchResult( const Word &query ) const {
  // Check if the query is a subsequence of the candidate and return a result
  // accordingly. This is done by simultaneously going through the characters of
  // the query and the candidate. If both characters match, we move to the next
  // character in the query and the candidate. Otherwise, we only move to the
  // next character in the candidate. The matching is a combination of smart
  // base matching and smart case matching. If there is no character left in the
  // query, the query is not a subsequence and we return an empty result. If
  // there is no character left in the candidate, the query is a subsequence and
  // we return a result with the query, the candidate, the sum of indexes of the
  // candidate where characters matched, and a boolean that is true if the query
  // is a prefix of the candidate.

  if ( query.IsEmpty() ) {
    return Result( this, &query, 0, false );
  }

  if ( Length() < query.Length() ) {
    return Result();
  }

  size_t query_index = 0;
  size_t candidate_index = 0;
  size_t index_sum = 0;

  const CharacterSequence &query_characters = query.Characters();
  const CharacterSequence &candidate_characters = Characters();

  auto query_character_pos = query_characters.begin();
  auto candidate_character_pos = candidate_characters.begin();

  for ( ; candidate_character_pos != candidate_characters.end();
          ++candidate_character_pos, ++candidate_index ) {

    const auto &candidate_character = *candidate_character_pos;
    const auto &query_character = *query_character_pos;

    if ( query_character->MatchesSmart( *candidate_character ) ) {
      index_sum += candidate_index;

      ++query_character_pos;
      if ( query_character_pos == query_characters.end() ) {
        return Result( this,
                       &query,
                       index_sum,
                       candidate_index == query_index );
      }

      ++query_index;
    }
  }

  return Result();
}
*/

Result Candidate::QueryMatchResult( const Word &query ) const {
    if ( query.IsEmpty() ) {
        return Result( this, 0);
    }

    if ( Length() < query.Length() ) {
        return Result();
    }

    const auto &candidate_chars = Characters(), &query_chars = query.Characters();
    auto query_iter = query_chars.begin(), query_end = query_chars.end();
    auto query_begin = query_iter;
    auto candidate_begin = candidate_chars.begin();

    // 记录连续匹配的起点 [query_start, candidate_start]
    std::vector<std::pair<decltype(query_iter), decltype(candidate_chars.begin())>> match_pairs;
    match_pairs.reserve(query_chars.size() + 1);
    bool continuous = false;

    for (auto candidate_iter = candidate_begin, e = candidate_chars.end(); candidate_iter != e; ++candidate_iter) {
        const auto &candidate_char = *candidate_iter;
        const auto &query_char = *query_iter;
        if (query_char->MatchesSmart(*candidate_char)) {
            if (!continuous) {
                continuous = true;
                match_pairs.emplace_back(query_iter, candidate_iter);
            }
            ++query_iter;
            if ( query_iter == query_end ) {
                match_pairs.emplace_back(query_end, candidate_iter+1);
                goto calculate_score;
            }
        } else {
            continuous = false;
        }
    }
    // query_chars not match.
    return Result();

calculate_score:
    // 有push才会进这个分支.
    const int64_t BASIC_SCORE = 1000;
    // the last char will get some extra bonus
    size_t word_boundary_count = LongestCommonSubsequenceLength(WordBoundaryChars(), query_chars);
    { // find longest continuous and try fix match early
      size_t longest_start_index = 0, longest_count = 0;
      for (auto b = match_pairs.cbegin(), it = b + 1, e = match_pairs.cend(); it != e; ++it) {
          size_t len = it->first - (it-1)->first;
          if (len >= longest_count) {
              longest_start_index = it - 1 - b;
              longest_count = len;
          }
      }
      // 连续匹配可能因为前缀被前面字符串部分匹配，而导致最佳连续数算错。
      // 如: aaabcd, abcd中a会匹配第一个a,导致连续数只有3，但应该是4。
      if (longest_count >= 2 && longest_start_index > 0) { // 至少2个以上连续时才尝试修正.
          auto previous_unmatch_candidate_iter = match_pairs[longest_start_index].second-1;
          auto origin_start = match_pairs[longest_start_index].first;
          auto extend_start_to = origin_start;
          do {
              // extend_start_to won't == 0
              if ( (*(extend_start_to - 1))->MatchesSmart(**previous_unmatch_candidate_iter) ) {
                  --extend_start_to;
                  --previous_unmatch_candidate_iter;
              } else {
                  break;
              }
          } while( extend_start_to != query_begin );
          if (extend_start_to < origin_start) { // continuous extend, fix match data
              match_pairs[longest_start_index] = {extend_start_to, previous_unmatch_candidate_iter+1};
              auto end = match_pairs.begin() + longest_start_index, erase_start = end;
              while (erase_start > match_pairs.begin() && (erase_start-1)->first >= extend_start_to) {
                  --erase_start;
              }
              if (erase_start < end) {
                  match_pairs.erase(erase_start, end);
              }
          }
      }
    }

    size_t index_sum = 0;
    size_t change_case_count = 0;
    { // loop for calculate index_sum and change_case_count
        for (auto range = match_pairs.cbegin(), e = match_pairs.cend() - 1; range != e; ++range) {
            auto query_it = range->first;
            auto candidate_iter = range->second;
            auto next_query = (range+1)->first;
            for ( ; query_it != next_query; ++query_it, ++candidate_iter ) {
                index_sum += candidate_iter - candidate_begin;
                if ( **query_it != **candidate_iter ) { ++change_case_count; }
            }
        }
    }

    // 计算score

    // continue_count will increase when match,
    //  and get a lot of bonus when discontinue according to continue count.

    // word boundary give a lot of bonus according to similarity

    // front give a little priority to back
    // short give a little priority to long
    // match case give a little priority to convert case

    int64_t score = 0;
    if (word_boundary_count > 0) {
        // FIXME: 现在的 word_boundary_count算法只比对公用子串，但query中不匹配的部分不一定真的匹配到原字符串。
        double const word_boundary_char_utilization = word_boundary_count / (double)word_boundary_chars_.size();
        score += word_boundary_count * word_boundary_count * (1 + word_boundary_char_utilization * 2) * BASIC_SCORE;
    }
    for (auto it = match_pairs.begin() + 1, e = match_pairs.end(); it != e; ++it) {
        // FIXME: 都是连续的，但更多的字符会导致上面的WBC得更多的分，导致短小的单个单词选中不了。如dict vs XXXdictXXX
        // 按连续算时，WBC是不是不应该得那么多分，特别是按连续的匹配算时，其实根本没有匹配WBC。
        // 是不是应该尝试一种连续匹配和WBC匹配，取高分?
        auto len = it->first - (it-1)->first;
        if (len > 1) { // 相同字符3个以下时，WB分更高
            score += len * len * 2 * BASIC_SCORE;
        }
    }
    score -= candidate_chars.size() * 3; // longer length have less score
    score -= change_case_count; // change case have less score
    score -= index_sum; // match previous have lower index_sum, and give litte priority
    // 暂时不算最后的bonous
    // if (matched_pos.back() == candidate_chars.size() - 1) { // last char give a change to select easily, especially for short string
    //     score += 1500 / (candidate_chars.size() * candidate_chars.size()) * BASIC_SCORE;
    // }
    return Result(this, score);
}

} // namespace YouCompleteMe
