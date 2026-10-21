"""The GraphQL documents XING's own frontend sends to /xing-one/api, trimmed
to what a logged-out visitor can read (captured 2026-10-19 from the crate
bundles on static.xingcdn.com, where they live as graphql-js AST objects).

Introspection is off and enum values are "[Obfuscated]" in error messages,
so every enum literal here (SEMANTIC, SQUARE_256, JOB_ROLE…) is one the
bundles use. Fields that need a login (userInteractions, viewer.xingId,
bookmark state, social proof) are left out — anonymously they either come
back null or fail the whole field.

One document per operation name; fetch.graphql(op, variables) looks it up
in DOCS. Keep the operation names: the API refuses a request whose
operationName does not match the document."""

_SALARY = """
fragment Salary on Salary { currency amount }
fragment SalaryRange on SalaryRange { currency minimum maximum }
fragment SalaryEstimate on SalaryEstimate { currency minimum maximum median }
"""

_JOB_TEASER = """
fragment JobTeaser on VisibleJob {
  id
  slug
  url
  title
  activatedAt
  refreshedAt
  activeUntil
  paid
  topJob
  prioritized
  redirectsToThirdPartyUrl
  language
  jobCode
  remoteOptions
  employmentType { id localizationValue }
  careerLevel { id localizationValue }
  discipline { id localizationValue }
  industry { id localizationValue }
  location { city cityId region zipCode country { countryCode localizationValue } }
  locations { city region zipCode country { countryCode localizationValue } }
  companyInfo {
    companyNameOverride
    company {
      id
      companyName
      companySize
      industry { id localizationValue }
      links { public }
      logos { logo128px }
      kununuData { ratingAverage recommendationRate ratingCount }
    }
  }
  salary { ...Salary ...SalaryRange ...SalaryEstimate }
  application {
    __typename
    ... on UrlApplication { applyUrl }
    ... on EmailApplication { applyEmail }
  }
  summary: summaryV2 { content { introduction keyResponsibilities qualifications } }
}
"""

JOB_SEARCH = """
query JobSearchByQuery($query: JobSearchQueryInput!, $consumer: String!, $offset: Int, $limit: Int, $sort: String, $sincePeriod: SincePeriod, $returnAggregations: Boolean = true) {
  jobSearchByQuery(query: $query, consumer: $consumer, offset: $offset, limit: $limit, sort: $sort, sincePeriod: $sincePeriod, searchMode: SEMANTIC, returnAggregations: $returnAggregations) {
    boundedTotal { total bound countType }
    searchQuery {
      body {
        keywords
        location { text radius city { id name } }
        filterCollection {
          ... on JobFilterRemoteOption { entityId remoteOption { localizationValue } }
          ... on JobFilterCompany { entityId company { companyName } }
          ... on JobFilterEmploymentType { entityId employmentType { localizationValue } }
          ... on JobFilterCareerLevel { entityId careerLevel { localizationValue } }
          ... on JobFilterDiscipline { entityId discipline { localizationValue } }
          ... on JobFilterIndustry { entityId industry { localizationValue } }
          ... on JobFilterCountry { entityId country { localizationValue } }
          ... on JobFilterCity { entityId city { name } }
          ... on JobFilterSalary { min max }
        }
      }
    }
    collection {
      position
      descriptionHighlight
      jobDetail {
        __typename
        ... on UnauthorizedJob { id reason }
        ...JobTeaser
      }
      matchingHighlightsV2 {
        highlight { type localization { localizationValue } }
      }
    }
    aggregations {
      employmentTypes { id count employmentType { localizationValue } }
      careerLevels { id count careerLevel { localizationValue } }
      disciplines { id count discipline { localizationValue } }
      industries { id count industry { localizationValue } }
      countries { id count country { localizationValue } }
      cities { id count city { name } }
      remoteOptions { id remoteOption { localizationValue } }
    }
  }
}
""" + _SALARY + _JOB_TEASER

JOB_DETAILS = """
query GetJobDetails($slug: String!) {
  job(slug: $slug, enableTemplateData: true, enableXingCustomApplication: true) {
    __typename
    ... on UnauthorizedJob { id reason }
    ... on VisibleJob {
      ...JobTeaser
      keywords
      location { street }
      locations { street }
      screenOutCriteria { euWorkEligibility languageSkillsGerman }
      application {
        ... on JobXingApplication { applyServiceSettings { loggedoutApplicationsEnabled } }
        ... on JobXingCustomApplication { applyServiceSettings { loggedoutApplicationsEnabled } }
        ... on MessageApplication { contactUserId }
      }
      companyInfo {
        company {
          companySizeRange { min max }
          employeesCount
          address { street city country { countryCode localizationValue } }
          logos { logo256px }
          kununuData { companyProfileUrl }
        }
      }
      description {
        __typename
        ... on HtmlDescription { content }
        ... on ExternalUrlDescription { url proxyUrl htmlContent }
        ... on TemplateData {
          genericDescription
          companyDescriptionTitle companyDescriptionContent
          responsibilityTitle responsibilityContent
          skillsTitle skillsContent
          weOfferTitle weOfferContent
          contactInfoTitle contactInfoContent
          headerImage footerImage
          videoUrls { youtube vimeo }
          socialUrls { website facebook twitter youtube xing instagram pinterest tiktok kununu }
        }
      }
    }
  }
}
""" + _SALARY + _JOB_TEASER

SIMILAR_JOBS = """
query GetSimilarJobs($jobId: ID!, $limit: Int!, $consumer: String!) {
  viewer {
    similarJobs(jobId: $jobId, limit: $limit, consumer: $consumer) {
      collection {
        position
        job { __typename ... on UnauthorizedJob { id reason } ...JobTeaser }
      }
    }
  }
}
""" + _SALARY + _JOB_TEASER

COMPANY_PAGE = """
query EntityPage($id: SlugOrID!) {
  entityPageEX(id: $id) {
    __typename
    ... on EntityPage {
      id
      title
      slug
      slogan
      context { companyId }
      links { self }
      coverImage(dimensions: [{height: 468, width: 1872, reference: "desktop"}]) { url }
      logoImage(dimensions: [{height: 320, width: 320, reference: "medium"}]) { url }
      publicationStatus
      modules { collection { type } }
    }
    ... on EntityPageError { errorType errorCode }
    ... on EntityPageMoved { slug }
  }
  headerModule: entityPageShowModule(id: $id, moduleType: "header") {
    ... on EntityPageHeaderModule {
      content {
        __typename
        ... on EntityPageCompanyHeaderContent {
          followers(first: 0) { total }
          company { id employeesCount companySizeRange { min max } industry { id localizationValue } }
        }
        ... on EntityPagePublisherHeaderContent { followers(first: 0) { total } }
        ... on EntityPageTopicPageHeaderContent { followers(first: 0) { total } }
      }
    }
  }
  pagesAboutUs(id: $id) {
    ... on AboutEntity {
      headline: aboutHeadline
      summary: aboutSummary
      media(first: 20) {
        ... on EntityMediaConnection {
          edges {
            node {
              ... on EntityMedia {
                id
                description
                media(maxWidth: 1200, maxHeight: 900) {
                  __typename
                  ... on ScaledImage { url }
                  ... on EntityVideo { videoReferenceV2 }
                  ... on EntityExternalVideo { url externalLink }
                }
              }
            }
          }
        }
      }
    }
  }
  entityPageLocations(id: $id, limit: 10) {
    collection {
      id label city address addressSuffix postcode highlighted email websiteURL
      coordinates { latitude longitude }
      country { countryCode localizationValue }
      phoneNumber { number countryCode }
      faxNumber { number countryCode }
    }
  }
}
"""

COMPANY_EXTRA = """
query CompanyExtra($id: SlugOrID!) {
  company(id: $id) {
    id
    companyName
    companySize
    companySizeRange { min max }
    employeesCount
    phone
    industry { id localizationValue }
    address { street city country { countryCode localizationValue } }
    links { public }
    logos { logo128px logo256px }
    kununuData { ratingAverage recommendationRate ratingCount companyProfileUrl }
    relatedCompanies {
      collection {
        company {
          id
          companyName
          companySize
          industry { localizationValue }
          address { city country { localizationValue } }
          links { public }
          logos { logo128px }
          kununuData { ratingAverage }
        }
      }
    }
  }
}
"""

EMPLOYEES = """
query Employees($id: SlugOrID!, $first: Int, $query: CompanyEmployeesQueryInput!) {
  company(id: $id) {
    id
    companyName
    links { public }
    employees(first: $first, query: $query) {
      total
      edges {
        node {
          profileDetails {
            id
            firstName
            lastName
            displayName
            academicTitle
            gender
            pageName
            status { localizationValue }
            location { city country { countryCode localizationValue } }
            occupations { category headline subline summary }
            profileImage(size: SQUARE_256) { url }
            userFlags { displayFlag }
          }
        }
      }
    }
  }
}
"""

NEWS = """
query NewsListItems($id: ID!, $limit: Int, $until: String) {
  entityPageContentFeeds(id: $id, limit: $limit, until: $until, supportedObjectTypes: [PLAIN_TEXT_POSTING, LINK_SHARE_POSTING, IMAGE_POSTING, CONTENT_PAGE_ARTICLE, COMPANY_PAGE_ARTICLE, VIDEO_POSTING, ARTICLES_ARTICLE]) {
    collection {
      globalId
      publishedAt
      isPinned
      metadata { likesCount commentsCount }
      object {
        __typename
        ... on EntityPageContentFeedPostingPost {
          id
          comment
          createdAt
          attachment {
            __typename
            ... on PostingsImageAttachment { images(dimensions: [{height: 900, width: 1200, reference: "large"}]) { url } }
            ... on PostingsLinkAttachment { link { url title description cachedImageUrl sourceDomain } }
            ... on PostingsVideoAttachment { id videoV2 { ref } }
          }
        }
        ... on EntityPageContentFeedCompanyArticlePost {
          id comment permalink title description provider imageUrl
          video { id links { iframeUrl thumbnailsUrls } }
        }
        ... on EntityPageContentFeedArticlePost {
          globalId title description comment permalink provider
          image { srcWidth1232 }
          video { id links { iframeUrl thumbnailsUrls } }
        }
        ... on EntityPageContentFeedArticlesArticlePost {
          globalId title summary coverImageUrl visitUrl
          images(dimensions: [{height: 900, width: 1200, reference: "large"}]) { url }
        }
      }
    }
  }
}
"""

PROFILE = """
query profileLoProfile($id: SlugOrID!, $idAsString: String!) {
  profilePageMeta(profileId: $id) { indexable qualityIndex }
  profileStructuredData(slug: $idAsString) {
    jobTitle
    workLocation { address { addressCountry addressLocality } }
  }
  xingIdWithError(id: $id) {
    __typename
    ... on XingId {
      id firstName lastName displayName academicTitle gender pageName
      profileImage(size: SQUARE_256) { url }
      headerImage(options: [{width: 984, height: 480, reference: "984"}]) { url }
      hasDefaultHeaderImage
      userFlags { displayFlag }
      status { localizationValue }
      location { city displayLocation country { countryCode localizationValue } }
      occupations { category headline subline summary links { url } }
    }
    ... on ResponseError { errorCode errorMessage }
  }
  profileWorkExperience(profileId: $id) {
    collection {
      jobTitle beginDate endDate currentCompany companyName companyNotes localizedTimeString
      company { links { public } logos { logo256px } }
    }
  }
  profileEducation(profileId: $id) {
    education { primarySchool subject degree schoolName schoolNotes beginDate endDate localizedTimeString }
  }
  profileLanguageSkills(profileId: $id) {
    ... on LoggedOutProfileLanguageCollection { collection { language skillLevelId displayLanguage } }
  }
  profileSkills(userId: $id) { skills topSkills }
  similarProfiles(profileIdentifier: $id) {
    collection { id academicTitle firstName lastName businessCity businessCountry hasPhoto occupationTitle pageName photoUrl }
  }
}
"""

LOCATION_SUGGEST = """
query GetLocationSuggestions($consumer: String!, $text: String!, $language: String!, $countries: [String!], $limit: Int!) {
  autocompletionLocationsCity(consumer: $consumer, text: $text, language: $language, countries: $countries, limit: $limit) {
    collection { cityIdWithScrambling name adminArea3 adminArea formattedCountry }
  }
}
"""

ROLE_SUGGEST = """
query GetJobRoleSuggestions($consumer: String!, $text: String!, $limit: Int!) {
  autocompletionProfileJobRole(consumer: $consumer, text: $text, limit: $limit) { collection { suggestion } }
}
"""

DIRECTORY = """
query MasterDirectoryEntryByLetter($letter: String!, $limit: Int, $type: MasterDirectoryEntryType!) {
  masterDirectoryEntryByLetter(letter: $letter, limit: $limit, type: $type) { collection { displayName jobCount url } }
}
"""

LINKBOXES = """
query GetJobDetailsLinkboxes($location: String, $jobRole: String) {
  jobRoleLinkboxes: seoLinkBoxes(input: {serpType: "jobRole", jobRole: $jobRole}) {
    collection { kind entries { name url jobCount } }
  }
  localJobRoleLinkboxes: seoLinkBoxes(input: {serpType: "local-jobRole", jobRole: $jobRole, location: $location}) {
    collection { kind entries { name url jobCount } }
  }
}
"""

DOCS = {
    "JobSearchByQuery": JOB_SEARCH,
    "GetJobDetails": JOB_DETAILS,
    "GetSimilarJobs": SIMILAR_JOBS,
    "EntityPage": COMPANY_PAGE,
    "CompanyExtra": COMPANY_EXTRA,
    "Employees": EMPLOYEES,
    "NewsListItems": NEWS,
    "profileLoProfile": PROFILE,
    "GetLocationSuggestions": LOCATION_SUGGEST,
    "GetJobRoleSuggestions": ROLE_SUGGEST,
    "MasterDirectoryEntryByLetter": DIRECTORY,
    "GetJobDetailsLinkboxes": LINKBOXES,
}
